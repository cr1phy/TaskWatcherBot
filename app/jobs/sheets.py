import structlog

from ..models.cloudtext import CloudTextClient, Journal
from ..models.gsheets import GSheetsClient
from ..services.groups import GroupRegistry

logger = structlog.get_logger()


async def update_sheets(
    groups: GroupRegistry,
    cloudtext: CloudTextClient,
    gsheets: GSheetsClient,
) -> None:
    registered = await groups.get_all()
    ct_groups = await cloudtext.get_groups()
    group_id_map: dict[int, int] = {g.number: g.id for g in ct_groups}

    journals: dict[int, Journal] = {}
    for group_number in registered:
        ct_id = group_id_map.get(group_number)
        if not ct_id:
            continue
        try:
            journals[group_number] = await cloudtext.get_journal(ct_id)
        except Exception as e:
            await logger.aerror(
                "journal_fetch_failed", group_number=group_number, error=str(e)
            )

    await gsheets.update_all_sheets(journals)
