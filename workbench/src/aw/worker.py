from .context import build
from .settings import load
from .handlers import build as handlers
from .jobs import Worker
if __name__=='__main__':
 ctx=build(load());Worker(ctx.worker_db,ctx.db,handlers(ctx)).forever()
