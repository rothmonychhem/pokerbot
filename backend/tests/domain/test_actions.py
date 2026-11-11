import pytest
from pydantic import ValidationError

from pokerbot.domain import Action, ActionType, ForcedBetType, PublicAction, Street


def test_street_board_sizes() -> None:
    assert [s.board_size for s in Street] == [0, 3, 4, 5]


def test_constructors() -> None:
    assert Action.fold() == Action(type=ActionType.FOLD)
    assert Action.check().amount is None
    assert Action.call().type is ActionType.CALL
    assert Action.bet(300) == Action(type=ActionType.BET, amount=300)
    assert Action.raise_to(900).amount == 900


@pytest.mark.parametrize("kind", [ActionType.BET, ActionType.RAISE])
@pytest.mark.parametrize("amount", [None, 0, -5])
def test_bet_raise_need_positive_amount(kind: ActionType, amount: int | None) -> None:
    with pytest.raises(ValidationError):
        Action(type=kind, amount=amount)


@pytest.mark.parametrize("kind", [ActionType.FOLD, ActionType.CHECK])
def test_fold_check_reject_amount(kind: ActionType) -> None:
    with pytest.raises(ValidationError):
        Action(type=kind, amount=100)


def test_call_amount_optional_but_non_negative() -> None:
    assert Action(type=ActionType.CALL, amount=200).amount == 200
    with pytest.raises(ValidationError):
        Action(type=ActionType.CALL, amount=-1)


@pytest.mark.parametrize(
    "action",
    [Action.fold(), Action.check(), Action.call(), Action.bet(250), Action.raise_to(1_000)],
)
def test_action_json_round_trip(action: Action) -> None:
    assert Action.model_validate_json(action.model_dump_json()) == action


def test_public_action_round_trip_with_forced_bet() -> None:
    for kind in [ForcedBetType.BIG_BLIND, ActionType.RAISE]:
        pa = PublicAction(seat=2, street=Street.PREFLOP, kind=kind, amount=100, all_in=True)
        restored = PublicAction.model_validate_json(pa.model_dump_json())
        assert restored == pa
        assert type(restored.kind) is type(kind)


def test_public_action_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        PublicAction(seat=-1, street=Street.FLOP, kind=ActionType.CHECK)
    with pytest.raises(ValidationError):
        PublicAction(seat=0, street=Street.FLOP, kind=ActionType.BET, amount=-10)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Action.model_validate({"type": "fold", "foo": 1})


@pytest.mark.parametrize("raw", ["true", "1.0", '"100"', "100.5"])
def test_action_amount_is_strict(raw: str) -> None:
    with pytest.raises(ValidationError):
        Action.model_validate_json(f'{{"type": "bet", "amount": {raw}}}')


@pytest.mark.parametrize(
    ("street", "kind", "amount"),
    [
        (Street.FLOP, ActionType.BET, None),
        (Street.FLOP, ActionType.RAISE, 0),
        (Street.FLOP, ActionType.CHECK, 10),
        (Street.FLOP, ActionType.FOLD, 10),
        (Street.RIVER, ForcedBetType.ANTE, 5),
        (Street.PREFLOP, ForcedBetType.BIG_BLIND, None),
    ],
)
def test_public_action_kind_rules(
    street: Street, kind: ActionType | ForcedBetType, amount: int | None
) -> None:
    with pytest.raises(ValidationError):
        PublicAction(seat=0, street=street, kind=kind, amount=amount)


def test_model_copy_revalidates() -> None:
    with pytest.raises(ValidationError):
        Action.bet(100).model_copy(update={"amount": 0})
    assert Action.bet(100).model_copy(update={"amount": 300}).amount == 300
    assert Action.fold().model_copy() == Action.fold()


def test_street_order() -> None:
    assert [s.order for s in Street] == [0, 1, 2, 3]
