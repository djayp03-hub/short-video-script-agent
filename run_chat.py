"""Click Run in PyCharm to open the local conversation workspace."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from src.video_agent.chat_server import main

if __name__ == '__main__':
    raise SystemExit(main())
