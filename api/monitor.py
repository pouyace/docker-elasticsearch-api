from configparser import ConfigParser
from elasticsearch import Elasticsearch
from datetime import datetime
import time
import os

CONFIG_FILE_ELASTIC_SECTION = 'ElasticConfig'
CONFIG_FILE_API_SECTION = 'ElasticAPI'
CONFIG_FILE_PATH = 'elastic-api.ini'

ELASTIC_URL = 'elastic_url'
TEMPLATE = 'index_template_name'
PATTERN = 'index_template_pattern'
POINTER = 'index_rollover_alias'
INTERVAL = 'status_checking_interval'
MAX_INDICES = 'maximum_indices'
MAX_DOCS = 'maximmum_docs_per_index'



class ElasticConnection:
    def __init__(self, configs) -> None:
        self.configs = configs
        self.doConnect()

    def doConnect(self):
        auth = (self.configs["username"], self.configs["password"])
        self.elastic = Elasticsearch(self.configs[ELASTIC_URL], basic_auth=auth)
        print(self.elastic)


    def isConnected(self):
        return self.elastic.ping()


class ElasticAPI:
    def __init__(self, elastic, api) -> None:
        self.es = elastic        
        self.api = api
        self.checkTemplateExistance()

    def getIndexCountByCat(self, name):
        return self.es.cat.count(index=name, ignore=[503,400,404])

    def checkForRollOver(self):
        if self.currentDocs >= int(self.api[MAX_DOCS]):
            result = self.es.indices.rollover(alias=self.api[POINTER])
            print(result)

    def checkForDeletion(self):
        if self.indicesCount > int(self.api[MAX_INDICES]):
            earliestIndex =  min(list(self.es.indices.get_alias(index=self.api[TEMPLATE]).keys()))
            print("Deleting ", earliestIndex, " index...")
            result = self.es.indices.delete(index=earliestIndex, ignore=[400, 404])
            print(result)

    def start(self):
        while True:
            query = self.getIndexCountByCat(self.api[TEMPLATE])
            current_index = self.getIndexCountByCat(self.api[POINTER])

            self.indicesCount = int(self.es.count(index=self.api[TEMPLATE])['_shards']['total'])
            self.totalDocs = int(''.join(query.splitlines()).split(' ')[2])
            self.currentDocs = int(''.join(current_index.splitlines()).split(' ')[2])
            self.printResult()
            self.checkForRollOver()
            self.checkForDeletion()
            
            time.sleep(int(self.api[INTERVAL]))

    def printResult(self):
        now = datetime.now().time()
        print(now, '    Total: ', self.totalDocs, '    Current:', self.currentDocs, end="   ")
        print('    indices: ', self.indicesCount)

    def checkTemplateExistance(self):
        # Create index template
        template = {
            "mappings":{
                "properties":{
                    "foo":{
                        "type": "keyword"
                    }
                }
            },
            "aliases":{
                "elk-rollover":{} 
            }
        }
        initialIndex = self.api[TEMPLATE] + '-000001'
        index_template = 0
        first_index = 0
        try:
            tempalte_exists = self.es.indices.get_index_template(name=self.api[TEMPLATE], ignore=[404])
            if 'error' in tempalte_exists.keys():
                if 'not found' in tempalte_exists['error']['reason']:
                    index_template = self.es.indices.put_index_template(template=template, name=self.api[TEMPLATE], index_patterns=self.api[PATTERN])
                    print('index template created', index_template)
            else:
                print("Index template already exists")
            alias = {self.api[POINTER]: {}}
            first_index_exists = self.es.indices.get(index=initialIndex, ignore=[404])
            if 'error' in first_index_exists.keys():
                first_index = self.es.indices.create(index=initialIndex, aliases=alias, ignore=[400])
                print('Initial index created', first_index)
            else:
                print('Initial index already exists')
        except:
            print("An error occured")



def extractConfigs(filePath, config_section, api_section):
    elasticCOnfigs = {}
    elasticAPIs = {} 
    configParser = ConfigParser()
    fileFound = configParser.read(filePath)
    if len(fileFound) == 0:
        print("Could not read configuration file.")
        #raise ConfigFileNotFound
        return None, None
    hasElasticConfigs = configParser.has_section(config_section)
    hasElasticAPI = configParser.has_section(api_section)
    if not (hasElasticAPI and hasElasticConfigs):
        print('Could not extract configs from the file. Invalid syntax')
        return None, None
    elasticCOnfigs = dict(configParser.items(config_section))
    elasticAPIs = dict(configParser.items(api_section))
    
    if ELASTIC_URL not in elasticCOnfigs:
        elasticCOnfigs[ELASTIC_URL] = 'https://localhost:9200'
        print("Using default elastic url ", elasticCOnfigs[ELASTIC_URL])

    elasticCOnfigs['username'] = os.environ.get('username')
    elasticCOnfigs['password'] = os.environ.get('password')

    if TEMPLATE not in elasticAPIs:
        elasticAPIs[TEMPLATE] = 'default-template'
    if PATTERN not in elasticAPIs:
        elasticAPIs[PATTERN] = 'defalut-template-*'
    if POINTER not in elasticAPIs:
        elasticAPIs[POINTER] = 'default-template-pointer'
    if INTERVAL not in elasticAPIs:
        elasticAPIs[INTERVAL] = 60
    if MAX_DOCS not in elasticAPIs:
        elasticAPIs[MAX_DOCS] = 1000
    if MAX_INDICES not in elasticAPIs:
        elasticAPIs[MAX_INDICES] = 5
    
    return elasticCOnfigs, elasticAPIs


time.sleep(5)
print("Api started")
configs, api = extractConfigs(CONFIG_FILE_PATH, CONFIG_FILE_ELASTIC_SECTION, CONFIG_FILE_API_SECTION)
if (configs != None) and (api != None):
    print("Reading configuration file successful")
    print(configs)
    print(api)
else:
    print("Reading config file failed")
    exit(-1)

print("Waiting for connection")
elasticConnection = ElasticConnection(configs)
while not elasticConnection.isConnected():
    print("Waiting for response")
    time.sleep(5)
print("Connected to Elasticsearch.")

elasticAPI = ElasticAPI(elasticConnection.elastic, api)
elasticAPI.start()
