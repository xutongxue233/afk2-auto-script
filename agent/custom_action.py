from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


@AgentServer.custom_action("check_campaign_failure")
class CheckCampaignFailure(CustomAction):
    """Track consecutive battle failures and stop campaign if threshold reached."""

    _consecutive_failures = 0
    _max_failures = 3

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        params = argv.custom_action_param or {}
        max_failures = params.get("max_failures", 3)
        self.__class__._max_failures = max_failures

        self.__class__._consecutive_failures += 1
        current = self.__class__._consecutive_failures

        print(f"[CampaignFailure] Consecutive failures: {current}/{max_failures}")

        if current >= max_failures:
            print(f"[CampaignFailure] Reached max failures ({max_failures}), stopping campaign")
            self.__class__._consecutive_failures = 0
            return False

        return True


@AgentServer.custom_action("reset_campaign_failure")
class ResetCampaignFailure(CustomAction):
    """Reset the consecutive failure counter on victory."""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        CheckCampaignFailure._consecutive_failures = 0
        print("[CampaignFailure] Counter reset on victory")
        return True
