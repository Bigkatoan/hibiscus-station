"""The Blockly block catalogue (station-programs.md §5, "Implementation map" §B).

Normative for both sides: the server compiler accepts exactly these block types (anything else is
``unknown_block``) and the editor defines exactly these, with these field and input names. It is
served by ``GET /programs/blocks``. Built-in Blockly blocks keep their own names and fields
(``controls_if``, ``logic_compare``...); Hibiscus blocks are prefixed ``hb_``.

Serialized values: a ``variable`` field holds ``{"id": <variable id>}`` (resolved through the
workspace's ``variables`` list, whose ``type`` is ``"Number"`` or ``"String"``); every reference
field (``trajectory``, ``pose``, ``detector``, ``model``, ``camera``, ``button``, ``signal``) holds
the referenced id as a string.
"""

from __future__ import annotations

from hibiscus_station.programs.schemas import BlockCatalog, BlockField, BlockInput, BlockSpec

_F = BlockField
_I = BlockInput


def _stmt(
    type_: str, category: str, ast: str, fields: list[BlockField], inputs: list[BlockInput]
) -> BlockSpec:
    return BlockSpec.model_validate(
        {
            "type": type_,
            "category": category,
            "output": "statement",
            "ast": ast,
            "fields": fields,
            "inputs": inputs,
        }
    )


def _expr(
    type_: str, category: str, output: str, ast: str, fields: list[BlockField], inputs: list[BlockInput]
) -> BlockSpec:
    return BlockSpec.model_validate(
        {
            "type": type_,
            "category": category,
            "output": output,
            "ast": ast,
            "fields": fields,
            "inputs": inputs,
        }
    )


TIMEOUT = _F(name="TIMEOUT", kind="number", min=0.1, max=86400, default=30, optional=True)

BLOCKS: list[BlockSpec] = [
    # ---------------------------------------------------------------- start
    BlockSpec(
        type="hb_start",
        category="start",
        output="hat",
        ast="program",
        fields=[],
        inputs=[_I(name="DO", kind="statement")],
    ),
    # ---------------------------------------------------------------- motion
    _stmt(
        "hb_play_trajectory",
        "motion",
        "play_trajectory",
        [
            _F(name="TRAJECTORY", kind="trajectory"),
            _F(name="SPEED", kind="number", min=10, max=150, default=100),
        ],
        [],
    ),
    _stmt(
        "hb_move_to_pose",
        "motion",
        "move_to_pose",
        [_F(name="POSE", kind="pose"), _F(name="SPEED", kind="number", min=1, max=90, default=30)],
        [],
    ),
    _stmt(
        "hb_gripper",
        "motion",
        "gripper",
        [
            _F(name="ACTION", kind="dropdown", options=["open", "close", "set"], default="open"),
            _F(name="PERCENT", kind="number", min=0, max=100, default=50, optional=True),
        ],
        [],
    ),
    _stmt("hb_go_home", "motion", "go_home", [], []),
    _stmt("hb_relax_arm", "motion", "relax_arm", [], []),
    # ---------------------------------------------------------------- ai
    _stmt(
        "hb_run_model_for",
        "ai",
        "run_model",
        [
            _F(name="MODEL", kind="model"),
            _F(name="TASK", kind="text", default="", optional=True),
            _F(name="SECONDS", kind="number", min=0.1, max=600, default=10),
        ],
        [],
    ),
    _stmt(
        "hb_run_model_until",
        "ai",
        "run_model",
        [
            _F(name="MODEL", kind="model"),
            _F(name="TASK", kind="text", default="", optional=True),
            TIMEOUT,
        ],
        [_I(name="UNTIL", kind="condition"), _I(name="ON_TIMEOUT", kind="statement", optional=True)],
    ),
    # ---------------------------------------------------------------- control
    _stmt(
        "controls_if",
        "control",
        "if",
        [],
        [
            _I(name="IF", kind="condition", repeated=True),
            _I(name="DO", kind="statement", repeated=True),
            _I(name="ELSE", kind="statement", optional=True),
        ],
    ),
    _stmt(
        "controls_repeat_ext",
        "control",
        "repeat",
        [],
        [_I(name="TIMES", kind="value", check="number"), _I(name="DO", kind="statement")],
    ),
    _stmt("hb_repeat_forever", "control", "forever", [], [_I(name="DO", kind="statement")]),
    _stmt(
        "controls_whileUntil",
        "control",
        "while",
        [_F(name="MODE", kind="dropdown", options=["WHILE", "UNTIL"], default="WHILE")],
        [_I(name="BOOL", kind="condition"), _I(name="DO", kind="statement")],
    ),
    _stmt("hb_wait", "control", "wait", [], [_I(name="SECONDS", kind="value", check="number")]),
    _stmt(
        "hb_wait_until",
        "control",
        "wait_until",
        [TIMEOUT],
        [_I(name="COND", kind="condition"), _I(name="ON_TIMEOUT", kind="statement", optional=True)],
    ),
    _stmt("hb_stop_program", "control", "stop", [], []),
    # ---------------------------------------------------------------- conditions
    _expr(
        "logic_operation",
        "conditions",
        "boolean",
        "logic",
        [_F(name="OP", kind="dropdown", options=["AND", "OR"])],
        [_I(name="A", kind="condition"), _I(name="B", kind="condition")],
    ),
    _expr("logic_negate", "conditions", "boolean", "not", [], [_I(name="BOOL", kind="condition")]),
    _expr(
        "logic_boolean",
        "conditions",
        "boolean",
        "bool",
        [_F(name="BOOL", kind="dropdown", options=["TRUE", "FALSE"])],
        [],
    ),
    _expr(
        "logic_compare",
        "conditions",
        "boolean",
        "compare",
        [_F(name="OP", kind="dropdown", options=["EQ", "NEQ", "LT", "LTE", "GT", "GTE"])],
        [_I(name="A", kind="value", check="any"), _I(name="B", kind="value", check="any")],
    ),
    _expr(
        "hb_camera_sees",
        "conditions",
        "boolean",
        "camera_sees",
        [
            _F(name="CAMERA", kind="camera", optional=True),
            _F(name="DETECTOR", kind="detector"),
            _F(name="LABEL", kind="label"),
        ],
        [],
    ),
    _expr(
        "hb_detector_confidence",
        "conditions",
        "number",
        "detector_confidence",
        [
            _F(name="CAMERA", kind="camera", optional=True),
            _F(name="DETECTOR", kind="detector"),
            _F(name="LABEL", kind="label", optional=True),
        ],
        [],
    ),
    _expr(
        "hb_button_pressed", "operator", "boolean", "button_pressed", [_F(name="BUTTON", kind="button")], []
    ),
    _expr("hb_key_pressed", "operator", "boolean", "key_pressed", [_F(name="KEY", kind="key")], []),
    _stmt(
        "hb_ask_operator",
        "operator",
        "ask",
        [
            _F(name="QUESTION", kind="text"),
            _F(name="CHOICES", kind="text", default="yes,no"),  # comma separated, 1-8 choices
            _F(name="VAR", kind="variable"),
            _F(name="TIMEOUT", kind="number", min=0.1, max=86400, optional=True),
        ],
        [],
    ),
    _expr("hb_gripper_holding", "conditions", "boolean", "gripper_holding", [], []),
    _expr(
        "hb_joint_compare",  # compiles to compare(joint_value(JOINT), number(DEG))
        "conditions",
        "boolean",
        "compare",
        [
            _F(name="JOINT", kind="joint"),
            _F(name="OP", kind="dropdown", options=["LT", "GT"]),
            _F(name="DEG", kind="number", min=-360, max=360, default=0),
        ],
        [],
    ),
    _expr("hb_joint_value", "conditions", "number", "joint_value", [_F(name="JOINT", kind="joint")], []),
    _expr(
        "hb_near_pose",
        "conditions",
        "boolean",
        "near_pose",
        [_F(name="POSE", kind="pose"), _F(name="TOLERANCE", kind="number", min=0.1, max=45, default=3)],
        [],
    ),
    _expr(
        "hb_motor_temp_compare",  # compiles to compare(motor_temp(MOTOR|null), number(TEMP))
        "conditions",
        "boolean",
        "compare",
        [
            _F(name="MOTOR", kind="motor", default="any"),  # "any" = hottest motor
            _F(name="OP", kind="dropdown", options=["GT", "LT"]),
            _F(name="TEMP", kind="number", min=0, max=100, default=50),
        ],
        [],
    ),
    _expr(
        "hb_motor_temp",
        "conditions",
        "number",
        "motor_temp",
        [_F(name="MOTOR", kind="motor", default="any")],
        [],
    ),
    _expr(
        "hb_signal_equals",
        "conditions",
        "boolean",
        "signal_equals",
        [_F(name="NAME", kind="signal"), _F(name="VALUE", kind="text")],  # numeric text -> number
        [],
    ),
    _expr("hb_signal_value", "conditions", "number", "signal_value", [_F(name="NAME", kind="signal")], []),
    _expr(
        "hb_message_received",
        "conditions",
        "boolean",
        "message_received",
        [
            _F(name="SOURCE", kind="dropdown", options=["http", "mqtt"], default="http"),
            _F(name="NAME", kind="text"),
        ],
        [],
    ),
    # ---------------------------------------------------------------- data
    _expr("math_number", "data", "number", "number", [_F(name="NUM", kind="number")], []),
    _expr(
        "math_arithmetic",
        "data",
        "number",
        "arith",
        [_F(name="OP", kind="dropdown", options=["ADD", "MINUS", "MULTIPLY", "DIVIDE", "POWER"])],
        [_I(name="A", kind="value", check="number"), _I(name="B", kind="value", check="number")],
    ),
    _expr(
        "math_modulo",
        "data",
        "number",
        "arith",
        [],
        [_I(name="DIVIDEND", kind="value", check="number"), _I(name="DIVISOR", kind="value", check="number")],
    ),
    _expr(
        "math_random_int",
        "data",
        "number",
        "random_int",
        [],
        [_I(name="FROM", kind="value", check="number"), _I(name="TO", kind="value", check="number")],
    ),
    _expr("text", "data", "text", "text", [_F(name="TEXT", kind="text")], []),
    _expr(
        "text_join", "data", "text", "join", [], [_I(name="ADD", kind="value", check="any", repeated=True)]
    ),
    _expr("variables_get", "data", "number", "var", [_F(name="VAR", kind="variable")], []),
    _stmt(
        "variables_set",
        "data",
        "set_var",
        [_F(name="VAR", kind="variable")],
        [_I(name="VALUE", kind="value", check="any")],
    ),
    _stmt(
        "math_change",
        "data",
        "change_var",
        [_F(name="VAR", kind="variable")],
        [_I(name="DELTA", kind="value", check="number")],
    ),
    # ---------------------------------------------------------------- output
    _stmt("hb_log", "output", "log", [], [_I(name="TEXT", kind="value", check="any")]),
    _stmt(
        "hb_notify",
        "output",
        "notify",
        [_F(name="WEBHOOK", kind="checkbox", default=False)],
        [_I(name="TEXT", kind="value", check="any")],
    ),
    _stmt(
        "hb_set_signal",
        "output",
        "set_signal",
        [_F(name="NAME", kind="signal")],
        [_I(name="VALUE", kind="value", check="any")],
    ),
]

CATALOG = BlockCatalog(blocks=BLOCKS)
BLOCK_TYPES = frozenset(b.type for b in BLOCKS)
