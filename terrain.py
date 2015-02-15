from lettuce import *
import ConfigParser
import os

@before.each_feature#{{{
def setup_config(feature):
    calling_file = feature.described_at.file # get the path to the feature that called this step
    if '/ocean/' in calling_file:
        world.configfile = 'lettuce.ocean'
    elif '/landice/' in calling_file:
        world.configfile = 'lettuce.landice'
    else:
        print "Error: Unknown MPAS core was requested."
        exit()

    if not os.path.exists("%s/%s"%(os.getcwd(), world.configfile)):
        print "Please copy %s into the current directory %s"%(world.configfile, os.getcwd())
        print " and configure appropriately for your tests."
        print ""
        exit()

    world.configParser = ConfigParser.SafeConfigParser()
    world.configParser.read(world.configfile)

    world.clone = world.configParser.get("steps", "clone")
    world.build = world.configParser.get("steps", "build")
    world.run = world.configParser.get("steps", "run")
    
    world.compiler = world.configParser.get("building", "compiler")
    world.core = world.configParser.get("building", "core")
    if world.configParser.has_option("building", "flags"):
        world.build_flags = world.configParser.get("building", "flags")
    else:
        world.build_flags = ""
    world.testing_url = world.configParser.get("testing_repo", "test_cases_url")
    world.trusted_url = world.configParser.get("trusted_repo", "test_cases_url")

    world.base_dir = os.getcwd()
    if ( world.core == "ocean" ):
        world.executable = "ocean_forward_model"
    elif ( world.core == "landice" ):
        world.executable = "landice_model"
#}}}

@before.each_step#{{{
def setup_step(step):
    # Change directory to base_dir
    os.chdir(world.base_dir)
#}}}

@after.each_scenario#{{{
def teardown_some_scenario(scenario):
      # print any messages that got loaded
      try:
        print world.message
        del world.message
      except:
        pass

      # reset to world.basedir so the next scenario can work
      # in case we erred and were left stranded elsewhere
      try:
        os.chdir(world.base_dir)
      except:
        pass  # In some cases, if lettuce didn't get very far, world.basedir is not defined yet.
#}}}

