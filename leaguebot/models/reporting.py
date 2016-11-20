import asyncio

from leaguebot import app
from leaguebot.services import redis_queue, alerts
from leaguebot.static_constants import civilian, scout


def should_report(battle_info):
    # Don't report a single player dismantling their own things
    if len(battle_info['player_creep_counts']) < 2:
        return False
    # Don't report a single civilian or scout walking into someone's owned room and being shot down
    if not any(any(role != civilian and role != scout for role in creeps.keys())
               for player, creeps in battle_info['player_creep_counts'].items() if battle_info.get('owner') != player):
        return False
    return True


logger = app.logger


@asyncio.coroutine
def reporting_loop(loop):
    """
    :type loop: asyncio.events.AbstractEventLoop
    """
    while True:
        battle_data, database_key = yield from loop.run_in_executor(None, redis_queue.get_next_battle_to_report)

        if should_report(battle_data):
            success = yield from loop.run_in_executor(None, alerts.sendBattleMessage, battle_data)
            if not success:
                logger.debug("Successfully reported battle in {}.".format(battle_data['room']))
                yield from loop.run_in_executor(None, redis_queue.mark_battle_reported, database_key)
            else:
                logger.debug("Failed to reported battle in {}.".format(battle_data['room']))
                # Try again with the next battle to report in 30 seconds.
                yield from asyncio.sleep(30, loop=loop)
        else:
            logger.debug("Decided not to report battle in {}.".format(battle_data['room']))
            yield from loop.run_in_executor(None, redis_queue.mark_battle_reported, database_key)


def report_pending_battles():
    """
    Tries to reports all pending battles once.
    """
    first_failure = None  # for making sure we don't loop forever.`
    while True:
        result_tuple = redis_queue.get_next_battle_to_report(blocking=False)
        if result_tuple is None:
            break
        battle_data, database_key = result_tuple
        if battle_data['room'] == first_failure:
            break

        if should_report(battle_data):
            success = alerts.sendBattleMessage(battle_data)
            if success:
                logger.debug("Successfully reported battle in {}.".format(battle_data['room']))
                redis_queue.mark_battle_reported(database_key)
            else:
                logger.debug("Failed to reported battle in {}.".format(battle_data['room']))
                first_failure = battle_data['room']
        else:
            logger.debug("Decided not to report battle in {}.".format(battle_data['room']))
            redis_queue.mark_battle_reported(database_key)
