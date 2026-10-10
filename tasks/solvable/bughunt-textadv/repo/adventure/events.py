"""Scripted events: messages that appear on a given turn or when a room is entered."""


def _fire(state, event):
    state.fired.add(event["id"])
    return event["text"]


def after_turn(state):
    """Texts of timed events whose ``turn`` equals the current turn counter (each fires once)."""
    out = []
    for event in state.world.events:
        if event.get("turn") == state.turn and event["id"] not in state.fired:
            out.append(_fire(state, event))
    return out


def on_enter(state):
    """Texts of events attached to the room the player just entered (each fires once)."""
    out = []
    for event in state.world.events:
        if event.get("enter") == state.room and event["id"] not in state.fired:
            out.append(_fire(state, event))
    return out
