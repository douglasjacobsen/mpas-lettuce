from lettuce import *
import subprocess
import ConfigParser
import os

dev_null = open(os.devnull, 'w')

@before.all#{{{
def check_environment():
	if not os.environ.has_key("NETCDF"):
		print "Error: The NETCDF environment variable must be defined to use MPAS"
		exit()

	if not os.environ.has_key("PNETCDF"):
		print "Error: The PNETCDF environment variable must be defined to use MPAS"
		exit()

	if not os.environ.has_key("PIO"):
		print "Error: The PIO environment variable must be defined to use MPAS"
		exit()

	world.feature_count = 0
#}}}

@before.each_feature#{{{
def setup_config(feature):
	world.feature_count += 1
	if world.feature_count == 1:  # the clone/checkout/build actions should only happen before the first feature

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

		if world.configParser.has_option("lettuce_actions", "clone"):
		  world.clone = world.configParser.getboolean("lettuce_actions", "clone")
		else:
		  world.clone = False

		if world.configParser.has_option("lettuce_actions", "build"):
		  world.build = world.configParser.getboolean("lettuce_actions", "build")
		else:
		  world.build = False

		if world.configParser.has_option("lettuce_actions", "run"):
		  world.run = world.configParser.getboolean("lettuce_actions", "run")
		else:
		  world.run = False

		if world.clone == True:
		  print 'Lettuce will clone MPAS if needed.'
		else:
		  print 'Lettuce will NOT attempt to clone MPAS.'

		if world.build == True:
		  print 'Lettuce will build MPAS if needed.'
		else:
		  print 'Lettuce will NOT attempt to build MPAS.'

		if world.run == True:
		  print 'Lettuce will run MPAS.'
		else:
		  print 'Lettuce will NOT attempt to run MPAS.'

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

		print ' '

		# Setup both "trusted" and "testing" code directories.  This loop ensures they are setup identically.
		for testtype in ('trusted', 'testing'):
			need_to_build = False

			if ( world.clone == True ):
				print '----------------------------'

				# Clone repo
				# MH: Below I've switched to checkout a detached head rather than making a local branch.
				# Making a local branch failed if the branch name already existed (i.e., with 'master' which is automatically created during the clone)

				try:
					os.chdir("%s/%s"%(world.base_dir, testtype))
					HEAD_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=dev_null)
					need_to_clone = False # if the dir exists AND we got a hash, then this directory is a git repo
				except:
					need_to_clone = True  # if we fail to enter the dir or fail to get a hash then call this directory bad

				os.chdir(world.base_dir) # return to base_dir in case not already there

				if need_to_clone:
					need_to_build = True # set this for later - we definitely need to build if we don't even have a clone...
					# delete dir if it exists
					if os.path.exists("%s/%s"%(world.base_dir, testtype)):
						shutil.rmtree("%s/%s"%(world.base_dir, testtype))

					# Clone repo specified
					print "Cloning " + testtype + " repository."
					command = "git"
					arg1 = "clone"
					arg2 = "%s"%world.configParser.get(testtype+"_repo", "url")
					arg3 = testtype
					subprocess.check_call([command, arg1, arg2, arg3], stdout=dev_null, stderr=dev_null)
					os.chdir("%s/%s"%(world.base_dir, testtype))
					print "Checking out " + testtype + " branch."
					command = "git"
					arg1 = "checkout"
					arg2 = "origin/%s"%world.configParser.get(testtype+"_repo", "branch")
					subprocess.check_call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)  # this version checks out a detached head
					os.chdir(world.base_dir) # return to base_dir in case not already there

				# ---- Didn't need to make a new clone -----
				else:  # We don't need to clone, but that doesn't mean the branch or the executable are up to date
					os.chdir("%s/%s"%(world.base_dir, testtype))
					# make a temporary remote to get the most current version of the specified repo
					remotes = subprocess.check_output(['git', 'remote'], stderr=dev_null)
					if 'statuscheck' in remotes:
						# need to delete this remote first
						subprocess.check_call(['git', 'remote', 'rm', 'statuscheck'], stdout=dev_null, stderr=dev_null)

					subprocess.check_call(['git', 'remote', 'add', 'statuscheck', "%s"%world.configParser.get(testtype+"_repo", "url")], stdout=dev_null, stderr=dev_null)
					subprocess.check_call(['git', 'fetch', 'statuscheck'], stdout=dev_null, stderr=dev_null)
					# get the hash of the specified branch
					try:
						requested_hash = subprocess.check_output(['git', 'rev-parse', "statuscheck/%s"%world.configParser.get(testtype+"_repo", "branch")], stderr=dev_null)
					except:
						requested_hash = subprocess.check_output(['git', 'rev-parse', "%s"%world.configParser.get(testtype+"_repo", "branch")], stderr=dev_null)  # perhaps they just specified a hash instead of branch name, in which case don't include the remote - but still use rev-parse to get the FULL hash.
						#print requested_hash, HEAD_hash, '\n'

					if requested_hash == HEAD_hash:
						print 'Current ' + testtype + ' clone and branch are up to date.'
						need_to_build = False
						# Now remove the remote
						remotes = subprocess.check_output(['git', 'remote'], stderr=dev_null)
						if 'statuscheck' in remotes:
							subprocess.check_call(['git', 'remote', 'rm', 'statuscheck'], stdout=dev_null, stderr=dev_null)

					else:
						print 'Updating ' + testtype + ' HEAD to specified repository and branch.'
						need_to_build = True
						# Checkout the specified branch (as detached head) because it either is a different URL/branch or is newer (or older) than the current detached head
						try:
							subprocess.check_call(['git', 'checkout', requested_hash], stdout=dev_null, stderr=dev_null)
						except:
							exit("Lettuce encountered an error in trying to git checkout: " + requested_hash)

						remotes = subprocess.check_output(['git', 'remote'], stderr=dev_null)
						if 'origin' in remotes:
							subprocess.check_call(['git', 'remote', 'rm', 'origin'], stdout=dev_null, stderr=dev_null)

						if 'statuscheck' in remotes:
							subprocess.check_call(['git', 'remote', 'rename', 'statuscheck', 'origin'], stdout=dev_null, stderr=dev_null)

						# Clean the build of the core we're trying to build
						print "   -- Running make clean CORE=%s"%world.configParser.get("building", "core")
						subprocess.check_call(['make', 'clean', "CORE=%s"%world.configParser.get("building", "core")], stdout=dev_null, stderr=dev_null)

						os.chdir(world.base_dir) # return to base_dir in case not already there

				if ( world.build == True ):
					# Build executable
					if need_to_build or not os.path.exists("%s/%s/%s"%(world.base_dir, testtype, world.executable)):
						print "Building " + testtype + " executable."
						os.chdir("%s/%s"%(world.base_dir, testtype))
						args = ["make",]
						args.append("%s"%world.compiler)
						args.append("CORE=%s"%world.core)
						# Add any optional build flags specified, but don't add empty strings cause subprocess doesn't like them.
						for argstring in [x for x in world.build_flags.split(" ") if x]:  # this list comprehension ignores empty strings because the emptry string is 'falsy' in python.
							args.append(argstring)

						subprocess.check_call(args, stdout=dev_null, stderr=dev_null)
						if testtype == 'trusted':
							world.trusted_executable = "%s/%s"%(os.getcwd(), world.executable)
						elif testtype == 'testing':
							world.testing_executable = "%s/%s"%(os.getcwd(), world.executable)

						os.chdir("%s"%(world.base_dir))

		print '----------------------------'
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

	  # reset to world.base_dir so the next scenario can work
	  # in case we erred and were left stranded elsewhere
	  try:
		os.chdir(world.base_dir)
	  except:
		pass  # In some cases, if lettuce didn't get very far, world.base_dir is not defined yet.
#}}}

