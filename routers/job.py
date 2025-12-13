
"""
异步任务队列 API
"""
from fastapi import APIRouter, Depends
from arq.connections import ArqRedis, create_pool
from arq.connections import RedisSettings
from config import settings
from dependencies import verify_api_key
from services.job_queue import redis_settings

router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])

async def get_redis() -> ArqRedis:
    pool = await create_pool(redis_settings)
    yield pool
    await pool.close()

@router.post("/", dependencies=[Depends(verify_api_key)])
async def create_job(url: str, method: str = "GET"):
    """提交一个异步采集任务"""
    pool = await create_pool(redis_settings)
    job = await pool.enqueue_job('scrape_url_task', url, method=method)
    await pool.close()
    return {"job_id": job.job_id, "status": "queued", "url": url}

@router.get("/{job_id}", dependencies=[Depends(verify_api_key)])
async def get_job_status(job_id: str):
    """查询任务状态"""
    # 注意：ARQ 的 job 结果默认只在 Redis 保留一段时间
    # 实际生产中建议将结果存入数据库
    pool = await create_pool(redis_settings)
    from arq.jobs import Job
    try:
        job = Job(job_id, redis=pool)
        status = await job.status()
        result = await job.result()
        info = await job.info()
        await pool.close()
        return {
            "job_id": job_id,
            "status": status,
            "result": result,
            "enqueue_time": info.enqueue_time if info else None
        }
    except Exception as e:
        await pool.close()
        return {"error": str(e)}
