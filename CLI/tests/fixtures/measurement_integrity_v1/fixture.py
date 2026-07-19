import asyncio


def error_object_after_failure():
    try:
        important_operation()
    except Exception:
        return {"status": "error", "success": False}


async def supervised_background_work():
    task = asyncio.create_task(work())
    await task
