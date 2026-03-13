from aiogram.fsm.state import State, StatesGroup


class LinkingState(StatesGroup):
    GettingName = State()
    ChoosingStudent = State()
