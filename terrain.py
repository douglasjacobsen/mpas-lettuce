from lettuce import *

@after.each_scenario
def teardown_some_scenario(scenario):
      # print any messages that got loaded
      try:
        print world.message
        del world.message
      except:
        pass

