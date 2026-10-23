from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

cache = Cache()
csrf = CSRFProtect()
limiter = Limiter(get_remote_address)