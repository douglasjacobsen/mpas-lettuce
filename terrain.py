from lettuce import *
import os

@after.each_scenario
def teardown_some_scenario(scenario):
      # print any messages that got loaded
      try:
        print world.message
        del world.message
      except:
        pass

      # reset to world.basedir so the next scenario can work
      # in case we erred and were left stranded elsewhere
      os.chdir(world.basedir)

