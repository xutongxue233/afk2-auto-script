import sys
from pathlib import Path

from maa.agent.agent_server import AgentServer
from maa.toolkit import Toolkit

import custom_reco
import custom_action


def main():
    Toolkit.init_option(str(Path(__file__).parent.parent))

    if len(sys.argv) < 2:
        print("Usage: python main.py <socket_id>")
        sys.exit(1)

    socket_id = sys.argv[-1]

    AgentServer.start_up(socket_id)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()
