import unittest

from layercfg import ConfigError, Field, Layer, Schema, args_layer, env_layer, load

SCHEMA = Schema({
    "db": {
        "host": Field(str, default="localhost"),
        "port": Field(int, default=5432),
        "pool": {"size": Field(int, default=4)},
    },
    "debug": Field(bool, default=False),
    "ratio": Field(float, default=0.5),
    "log_level": Field(str, default="info", choices=("debug", "info", "warn")),
    "tags": Field(list, default=["a"]),
    "ports": Field(list, item=int),
    "modes": Field(list, item=str, choices=("fast", "safe", "slow"), default=[]),
    "name": Field(str, required=True),
})
BASE = Layer("base", {"name": "svc"})


def errs(fn):
    with unittest.TestCase().assertRaises(ConfigError) as cm:
        fn()
    return cm.exception


class Coercion(unittest.TestCase):
    def load(self, data, schema=SCHEMA):
        return load(schema, [BASE, Layer("t", data, coerce=True)])

    def test_int(self):
        for text, want in (("42", 42), (" -3 ", -3), ("+7", 7), ("007", 7)):
            self.assertEqual(self.load({"db": {"port": text}}).get("db.port"), want)
        for bad in ("4.5", "1e3", "", "abc", "0x10", "1_000"):
            with self.subTest(bad=bad):
                e = errs(lambda: self.load({"db": {"port": bad}}))
                self.assertEqual([p for p, _ in e.errors], ["db.port"])

    def test_float(self):
        self.assertEqual(self.load({"ratio": "2.5"}).get("ratio"), 2.5)
        self.assertEqual(self.load({"ratio": " 3 "}).get("ratio"), 3.0)
        self.assertEqual(self.load({"ratio": "1e-2"}).get("ratio"), 0.01)
        for bad in ("nan", "inf", "-inf", "x", ""):
            with self.subTest(bad=bad):
                errs(lambda: self.load({"ratio": bad}))

    def test_bool(self):
        for text in ("true", "TRUE", " Yes ", "1", "on"):
            self.assertIs(self.load({"debug": text}).get("debug"), True)
        for text in ("false", "No", "0", "OFF", " off"):
            self.assertIs(self.load({"debug": text}).get("debug"), False)
        for bad in ("", "2", "maybe", "truee"):
            errs(lambda: self.load({"debug": bad}))

    def test_str_unchanged(self):
        self.assertEqual(self.load({"db": {"host": "  h "}}).get("db.host"), "  h ")

    def test_non_string_values_in_coerce_layer_stay_strict(self):
        self.assertEqual(self.load({"db": {"port": 9}}).get("db.port"), 9)
        errs(lambda: self.load({"db": {"port": True}}))
        errs(lambda: self.load({"db": {"port": 1.5}}))
        errs(lambda: self.load({"debug": 1}))

    def test_non_coerce_layer_rejects_strings(self):
        errs(lambda: load(SCHEMA, [BASE, Layer("t", {"db": {"port": "5"}})]))
        errs(lambda: load(SCHEMA, [BASE, Layer("t", {"debug": "true"})]))

    def test_unknown_keys_ignored_only_when_coerce(self):
        cfg = self.load({"nope": "1", "db": {"nope": "2", "pool": {"zzz": "1"}}})
        self.assertEqual(cfg.get("db.port"), 5432)
        e = errs(lambda: load(SCHEMA, [BASE, Layer("t", {"db": {"nope": 1}})]))
        self.assertEqual([p for p, _ in e.errors], ["db.nope"])

    def test_section_clashes_error_everywhere(self):
        for coerce in (True, False):
            e = errs(lambda: load(SCHEMA, [BASE, Layer("t", {"db": "x"}, coerce=coerce)]))
            self.assertEqual([p for p, _ in e.errors], ["db"])
            e = errs(lambda: load(SCHEMA, [BASE, Layer("t", {"debug": {"x": 1}}, coerce=coerce)]))
            self.assertEqual([p for p, _ in e.errors], ["debug"])

    def test_choices(self):
        self.assertEqual(self.load({"log_level": "warn"}).get("log_level"), "warn")
        e = errs(lambda: self.load({"log_level": "loud"}))
        self.assertEqual([p for p, _ in e.errors], ["log_level"])
        errs(lambda: load(SCHEMA, [BASE, Layer("t", {"log_level": "loud"})]))


class Lists(unittest.TestCase):
    def test_comma_split(self):
        cfg = load(SCHEMA, [BASE, Layer("t", {"ports": "80, 443,8080 "}, coerce=True)])
        self.assertEqual(cfg.get("ports"), [80, 443, 8080])

    def test_blank_is_empty_list(self):
        for text in ("", "   "):
            cfg = load(SCHEMA, [BASE, Layer("t", {"tags": text}, coerce=True)])
            self.assertEqual(cfg.get("tags"), [])

    def test_str_items_stripped(self):
        cfg = load(SCHEMA, [BASE, Layer("t", {"tags": " a , b,c"}, coerce=True)])
        self.assertEqual(cfg.get("tags"), ["a", "b", "c"])

    def test_bad_item(self):
        e = errs(lambda: load(SCHEMA, [BASE, Layer("t", {"ports": "80,http"}, coerce=True)]))
        self.assertEqual([p for p, _ in e.errors], ["ports"])

    def test_choices_per_element(self):
        cfg = load(SCHEMA, [BASE, Layer("t", {"modes": "fast,safe"}, coerce=True)])
        self.assertEqual(cfg.get("modes"), ["fast", "safe"])
        errs(lambda: load(SCHEMA, [BASE, Layer("t", {"modes": "fast,warp"}, coerce=True)]))
        errs(lambda: load(SCHEMA, [BASE, Layer("t", {"modes": ["fast", "warp"]})]))

    def test_real_lists_validated(self):
        cfg = load(SCHEMA, [BASE, Layer("t", {"ports": [1, 2]})])
        self.assertEqual(cfg.get("ports"), [1, 2])
        for bad in ({"ports": [1, "2"]}, {"ports": [True]}, {"ports": "1,2"}, {"ports": 5}, {"ports": (1, 2)}):
            with self.subTest(bad=bad):
                errs(lambda: load(SCHEMA, [BASE, Layer("t", bad)]))

    def test_float_items_accept_ints(self):
        schema = Schema({"w": Field(list, item=float)})
        self.assertEqual(load(schema, [Layer("t", {"w": [1, 2.5]})]).get("w"), [1.0, 2.5])

    def test_lists_replace_not_merge(self):
        cfg = load(SCHEMA, [BASE, Layer("a", {"tags": ["x", "y"]}), Layer("b", {"tags": ["z"]})])
        self.assertEqual(cfg.get("tags"), ["z"])

    def test_no_aliasing_of_defaults(self):
        cfg = load(SCHEMA, [BASE])
        cfg.get("tags").append("junk")
        cfg.as_dict()["tags"].append("junk2")
        for _, v in cfg.explain("tags"):
            v.append("junk3")
        self.assertEqual(load(SCHEMA, [BASE]).get("tags"), ["a"])
        self.assertEqual(SCHEMA.field("tags").default, ["a"])

    def test_no_aliasing_of_layer_data(self):
        data = {"tags": ["p"]}
        cfg = load(SCHEMA, [BASE, Layer("t", data)])
        cfg.get("tags").append("q")
        self.assertEqual(data["tags"], ["p"])

    def test_list_field_without_default_is_none(self):
        cfg = load(SCHEMA, [BASE])
        self.assertIsNone(cfg.get("ports"))
        self.assertIsNone(cfg.source("ports"))

    def test_bad_field_declarations(self):
        with self.assertRaises(ValueError):
            Field(list, item=list)
        with self.assertRaises(ValueError):
            Field(dict)


class Env(unittest.TestCase):
    def test_nested_and_lowercase(self):
        layer = env_layer({"APP_DB__HOST": "h", "APP_DB__POOL__SIZE": "9", "APP_LOG_LEVEL": "debug", "OTHER": "x"}, "APP")
        self.assertEqual(layer.data, {"db": {"host": "h", "pool": {"size": "9"}}, "log_level": "debug"})
        self.assertTrue(layer.coerce)
        self.assertEqual(layer.name, "env")
        self.assertEqual(env_layer({}, "APP", name="envvars").name, "envvars")

    def test_prefix_requires_underscore_and_case(self):
        layer = env_layer({"APPX_DEBUG": "1", "app_debug": "1", "APPDEBUG": "1", "APP_DEBUG": "1"}, "APP")
        self.assertEqual(layer.data, {"debug": "1"})

    def test_ignored_variables(self):
        layer = env_layer({"APP_": "x", "APP_A____B": "x", "APP___X": "y", "APP_DB__": "z", "APP_DEBUG": "1"}, "APP")
        self.assertEqual(layer.data, {"debug": "1"})

    def test_clash_more_specific_wins(self):
        layer = env_layer({"APP_DB": "x", "APP_DB__HOST": "h"}, "APP")
        self.assertEqual(layer.data, {"db": {"host": "h"}})
        layer = env_layer({"APP_DB__HOST": "h", "APP_DB": "x"}, "APP")
        self.assertEqual(layer.data, {"db": {"host": "h"}})

    def test_end_to_end(self):
        env = {"APP_DB__PORT": "6000", "APP_DEBUG": "yes", "APP_PORTS": "1,2", "APP_NAME": "from-env", "APP_UNKNOWN": "x"}
        cfg = load(SCHEMA, [env_layer(env, "APP")])
        self.assertEqual((cfg.get("db.port"), cfg.get("debug"), cfg.get("ports"), cfg.get("name")), (6000, True, [1, 2], "from-env"))

    def test_env_scalar_for_section_is_error(self):
        e = errs(lambda: load(SCHEMA, [BASE, env_layer({"APP_DB": "x"}, "APP")]))
        self.assertEqual([p for p, _ in e.errors], ["db"])

    def test_does_not_mutate_environ(self):
        env = {"APP_A": "1"}
        env_layer(env, "APP")
        self.assertEqual(env, {"APP_A": "1"})


class Args(unittest.TestCase):
    def test_parse(self):
        layer = args_layer(["db.port=1", "debug=true", "db.host=a=b", "tags="])
        self.assertEqual(layer.data, {"db": {"port": "1", "host": "a=b"}, "debug": "true", "tags": ""})
        self.assertTrue(layer.coerce)
        self.assertEqual(layer.name, "args")

    def test_later_wins_and_case_kept(self):
        self.assertEqual(args_layer(["a=1", "a=2"]).data, {"a": "2"})
        self.assertEqual(args_layer(["Db.Port=1"]).data, {"Db": {"Port": "1"}})

    def test_clash(self):
        self.assertEqual(args_layer(["db=x", "db.host=h"]).data, {"db": {"host": "h"}})
        self.assertEqual(args_layer(["db.host=h", "db=x"]).data, {"db": {"host": "h"}})

    def test_invalid_items(self):
        for bad in ("noequals", "=v", ".a=1", "a..b=1", "a.=1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    args_layer([bad])

    def test_precedence_over_env(self):
        cfg = load(SCHEMA, [env_layer({"APP_NAME": "e", "APP_DB__PORT": "1"}, "APP"), args_layer(["db.port=2"])])
        self.assertEqual(cfg.get("db.port"), 2)
        self.assertEqual(cfg.source("db.port"), "args")
        self.assertEqual(cfg.source("name"), "env")


class Errors(unittest.TestCase):
    def test_collects_everything_sorted(self):
        layers = [
            Layer("file", {"db": {"port": "x"}, "debug": 3, "nope": 1}),
            env_layer({"APP_RATIO": "abc", "APP_LOG_LEVEL": "loud"}, "APP"),
        ]
        e = errs(lambda: load(SCHEMA, layers))
        paths = [p for p, _ in e.errors]
        self.assertEqual(paths, ["db.port", "debug", "log_level", "name", "nope", "ratio"])
        for p in paths:
            self.assertIn(p, str(e))
        self.assertIn("file", dict(e.errors)["db.port"])
        self.assertIn("env", dict(e.errors)["ratio"])

    def test_same_path_two_layers_two_errors(self):
        e = errs(lambda: load(SCHEMA, [BASE, Layer("a", {"debug": 1}), Layer("b", {"debug": "x"})]))
        self.assertEqual([p for p, _ in e.errors], ["debug", "debug"])
        self.assertIn("a", e.errors[0][1])
        self.assertIn("b", e.errors[1][1])

    def test_required_missing(self):
        e = errs(lambda: load(SCHEMA, []))
        self.assertEqual([p for p, _ in e.errors], ["name"])

    def test_errors_are_tuples_and_exception_is_str(self):
        e = errs(lambda: load(SCHEMA, []))
        self.assertIsInstance(e.errors[0], tuple)
        self.assertIsInstance(str(e), str)


class Provenance(unittest.TestCase):
    def test_explain_order(self):
        cfg = load(SCHEMA, [BASE, Layer("file", {"db": {"port": 1}}), Layer("late", {"db": {"port": 2}})])
        self.assertEqual(cfg.explain("db.port"), [("defaults", 5432), ("file", 1), ("late", 2)])
        self.assertEqual(cfg.source("db.port"), "late")

    def test_defaults_only(self):
        cfg = load(SCHEMA, [BASE])
        self.assertEqual(cfg.explain("db.host"), [("defaults", "localhost")])
        self.assertEqual(cfg.source("db.host"), "defaults")

    def test_required_field_from_one_layer(self):
        cfg = load(SCHEMA, [BASE])
        self.assertEqual(cfg.explain("name"), [("base", "svc")])

    def test_unset_optional_field(self):
        cfg = load(SCHEMA, [BASE])
        self.assertEqual(cfg.explain("ports"), [])
        self.assertIsNone(cfg.source("ports"))

    def test_values_are_converted(self):
        cfg = load(SCHEMA, [BASE, env_layer({"APP_DB__PORT": "7"}, "APP")])
        self.assertEqual(cfg.explain("db.port"), [("defaults", 5432), ("env", 7)])

    def test_same_value_still_listed(self):
        cfg = load(SCHEMA, [BASE, Layer("same", {"db": {"port": 5432}})])
        self.assertEqual(cfg.explain("db.port"), [("defaults", 5432), ("same", 5432)])

    def test_unknown_path(self):
        cfg = load(SCHEMA, [BASE])
        for fn in (cfg.get, cfg.source, cfg.explain):
            with self.assertRaises(KeyError):
                fn("db.nope")
            with self.assertRaises(KeyError):
                fn("db")

    def test_as_dict_shape(self):
        cfg = load(SCHEMA, [BASE])
        d = cfg.as_dict()
        self.assertEqual(d["db"]["pool"], {"size": 4})
        self.assertEqual(d["name"], "svc")
        self.assertIsNone(d["ports"])


if __name__ == "__main__":
    unittest.main()
