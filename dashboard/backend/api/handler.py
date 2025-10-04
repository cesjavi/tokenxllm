from api.index import app
from mangum import Mangum

handler = Mangum(app)