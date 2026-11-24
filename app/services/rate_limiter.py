import logging
import math
import time
import uuid
from typing import Annotated

from fastapi import Depends, Request
from redis.exceptions import RedisError

from app.exceptions import RateLimited
from app.models import User

# the lua script that redis runs
# KEYS[1] is the redis key taht identifies which user's rate limit we're working with
# redis.call('ZREMRANGEBYSCORE',KEYS[1],0,now-window): removes sorted set entries whose score fall between 0 and now-window
# redis.call('ZCARD',KEYS[1]): after removing old reqs count the remaining ones
# local oldest=redis.call('ZRANGE',KEYS[1],0,0,'WITHSCORES'): retrieves oldest request with its score,to calculate when it'll leave the window, when the next request can be mad
# redis.call('ZADD',KEYS[1],now,ARGV[4]):ARGV[4] is the 4th arg passed to the lua script, the unique request ID

# lua script runs atomically, preventing concurrent requests from bypassing the limit ,ensures simultaneous requests can't bypass that limit because of race condition
LUA = """
local now,window,limit=tonumber(ARGV[1]),tonumber(ARGV[2]),tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE',KEYS[1],0,now-window) 


if redis.call('ZCARD',KEYS[1])>=limit then
    local oldest=redis.call('ZRANGE',KEYS[1],0,0,'WITHSCORES')
    return {0,tostring(tonumber(oldest[2])+window-now)}
    end
redis.call('ZADD',KEYS[1],now,ARGV[4])
redis.call('EXPIRE',KEYS[1],math.ceil(window))
return {1,'0'}

"""

log = logging.getLogger("rl")


class RateLimiter:
    # name identifies the endpoint, current_user is the dep that identifies the current user
    def __init__(self, name, limit, window, current_user):
        self.name = name
        self.limit = limit
        self.window = window
        self.current_user = current_user

    def dependency(self):
        async def check(request: Request, user: Annotated[User, Depends(self.current_user)]):
            key = f"rl:{self.name}:{user.id}"  # rl stands for rate-limiter
            if request.app.state.redis_pool is None:
                log.warning("rate limiter:redis is unavailable, letting request through")
                return
            if request.app.state.redis_pool is not None:
                try:
                    ok, retry = await request.app.state.redis_pool.eval(
                        LUA, 1, key, time.time(), self.window, self.limit, uuid.uuid4().hex
                    )  # 1 is the no of redis keys the script uses, use uuid.uuid4().hex instead of user_id as diff reqs from same user will get diff ids, will be treated differently(not the same), identifies the individual req
                except RedisError:  # if redis is unavailable
                    log.warning(
                        "rate limiter: Redis unavailable, letting the request through"
                    )  # called fail-open:if rl fails, the user can still acsess the endpoint
                    return

                if not (int(ok)):  # when ok=0, the req is not allowed
                    raise RateLimited(
                        "Too many requests",
                        headers={
                            "Retry-After": str(
                                max(1, math.ceil(float(retry)))
                            )  # wait atleast 1s, round up retry after(unit:s)
                        },
                    )

        return check
