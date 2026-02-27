from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context


@AgentServer.custom_recognition("detect_exit_dialog")
class DetectExitDialog(CustomRecognition):
    """Detect exit/quit confirmation dialog in the game."""

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        reco_detail = context.run_recognition(
            "FindCancelInDialog",
            argv.image,
            pipeline_override={
                "FindCancelInDialog": {
                    "recognition": "OCR",
                    "expected": ["取消", "Cancel"],
                    "roi": [200, 250, 880, 220],
                }
            },
        )

        if reco_detail is not None:
            return CustomRecognition.AnalyzeResult(
                box=reco_detail.box,
                detail="exit_dialog_detected",
            )

        return None
