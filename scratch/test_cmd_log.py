import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.append(str(Path(__file__).parent.parent))

from scripts.voice_bot import cmd_log

async def test_cmd_log():
    # 1. Create a dummy orchestrator.log
    log_file = Path(__file__).parent.parent / "orchestrator.log"
    log_file.write_text("Line 1: info\nLine 2: warning\nLine 3: error <tag>test</tag>\n" * 50, encoding="utf-8")
    
    # 2. Mock Update and Context
    update = MagicMock()
    message = AsyncMock()
    update.effective_message = message
    
    context = MagicMock()
    
    # 3. Call cmd_log
    print("Calling cmd_log with existing orchestrator.log...")
    await cmd_log(update, context)
    
    # Print what reply_text was called with (safely encode to ASCII with backslashreplace to avoid encoding errors)
    for call in message.reply_text.call_args_list:
        print("Reply sent:", str(call).encode("ascii", "backslashreplace").decode())

    # 4. Try with huge log
    print("\nCalling cmd_log with huge log...")
    log_file.write_text("A" * 10000, encoding="utf-8")
    message.reply_text.reset_mock()
    await cmd_log(update, context)
    for call in message.reply_text.call_args_list:
        print("Reply sent (huge log):", str(call).encode("ascii", "backslashreplace").decode())
        
    # Clean up
    log_file.unlink(missing_ok=True)

if __name__ == "__main__":
    asyncio.run(test_cmd_log())
