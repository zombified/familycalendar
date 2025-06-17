import argparse
import logging
import logging.config
import pathlib
import tomllib

parser = argparse.ArgumentParser()
parser.add_argument("config", help="path to ini config file")
args = parser.parse_args()

with open(args.config, "rb") as fin:
    config = tomllib.load(fin)

logging.config.dictConfig(config.get("logging", {}))
logger = logging.getLogger('familycal')

#sys_templates = Jinja2Templates(directory='src/sys_templates/')

def package_dir():
    return pathlib.Path(__file__).parent

