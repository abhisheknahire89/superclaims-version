"""Structured application logs; callers emit identifiers and error codes, never source text."""
import json,logging
from datetime import datetime,timezone
class JsonFormatter(logging.Formatter):
 def format(self,record):return json.dumps({'time':datetime.now(timezone.utc).isoformat(),'level':record.levelname,'component':record.name,'event':record.getMessage()},ensure_ascii=True)
def configure():
 handler=logging.StreamHandler();handler.setFormatter(JsonFormatter());logging.getLogger().handlers=[handler];logging.getLogger().setLevel(logging.INFO)
