import sys, os, glob, shutil, numpy, math
import subprocess
import ConfigParser

from netCDF4 import *
from netCDF4 import Dataset as NetCDFFile
from pylab import *

from lettuce import *

from collections import defaultdict
import xml.etree.ElementTree as ET

dev_null = open(os.devnull, 'w')

def seconds_to_timestamp(seconds):#{{{
	days = 0
	hours = 0
	minutes = 0

	if seconds >= 24*3600:
		days = int(seconds/(24*3600))
		seconds = seconds - int(days * 24 * 3600)

	if seconds >= 3600:
		hours = int(seconds/3600)
		seconds = seconds - int(hours*3600)

	if seconds >= 60:
		minutes = int(seconds/60)
		seconds = seconds - int(minutes*60)

	timestamp = "%4.4d_%2.2d:%2.2d:%2.2d"%(days, hours, minutes, seconds)
	return timestamp#}}}

@step(u'A setup test environment')#{{{
def setup_test_environment(step):
	calling_file = step.scenario.feature.described_at.file # get the path to the feature that called this step
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

	configParser = ConfigParser.SafeConfigParser()
	configParser.read(world.configfile)
	world.clone = configParser.get("steps", "clone")
	world.build = configParser.get("steps", "build")
	world.run = configParser.get("steps", "run")

	world.compiler = configParser.get("building", "compiler")
	world.core = configParser.get("building", "core")
	if world.core == "ocean":
		world.executable = "ocean_forward_model"
	elif world.core == "landice":
		world.executable = "landice_model"

	if configParser.has_option("building", "flags"):
		world.build_flags = configParser.get("building", "flags")
	else:
		world.build_flags = ""
	world.testing_url = configParser.get("testing_repo", "test_cases_url")
	world.trusted_url = configParser.get("trusted_repo", "test_cases_url")

	base_dir = os.getcwd()

	# Setup both "trusted" and "testing" code directories.  This loop ensures they are setup identically.
	for testtype in ('trusted', 'testing'):

		if ( world.clone == "YES" ):
			print '----------------------------'

			# Clone repo
			# MH: Below I've switched to checkout a detached head rather than making a local branch.
			# Making a local branch failed if the branch name already existed (i.e., with 'master' which is automatically created during the clone)

			try:
				os.chdir("%s/%s"%(base_dir, testtype))
				HEAD_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=dev_null)
				need_to_clone = False # if the dir exists AND we got a hash, then this directory is a git repo
			except:
				need_to_clone = True  # if we fail to enter the dir or fail to get a hash then call this directory bad
			os.chdir(base_dir) # return to basedir in case not already there

			if need_to_clone:
				need_to_build = True # set this for later - we definitely need to build if we don't even have a clone...
				# delete dir if it exists
				if os.path.exists("%s/%s"%(base_dir, testtype)):
					shutil.rmtree("%s/%s"%(base_dir, testtype))

				# Clone repo specified
				print "Cloning " + testtype + " respository. "
				command = "git"
				arg1 = "clone"
				arg2 = "%s"%configParser.get(testtype+"_repo", "url")
				arg3 = testtype
				subprocess.check_call([command, arg1, arg2, arg3], stdout=dev_null, stderr=dev_null)
				os.chdir("%s/%s"%(base_dir, testtype))
				print "Checking out " + testtype + " branch. "
				command = "git"
				arg1 = "checkout"
				arg2 = "origin/%s"%configParser.get(testtype+"_repo", "branch")
				subprocess.check_call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)  # this version checks out a detached head
				os.chdir(base_dir) # return to basedir in case not already there

			# ---- Didn't need to make a new clone -----
			else:  # We don't need to clone, but that doesn't mean the branch or the executable are up to date
				os.chdir("%s/%s"%(base_dir, testtype))
				# make a temporary remote to get the most current version of the specified repo
				remotes = subprocess.check_output(['git', 'remote'], stderr=dev_null)
				if 'statuscheck' in remotes:
					# need to delete this remote first
					print
					print remotes
					print
					subprocess.check_call(['git', 'remote', 'rm', 'statuscheck'], stdout=dev_null, stderr=dev_null)
				subprocess.check_call(['git', 'remote', 'add', 'statuscheck', "%s"%configParser.get(testtype+"_repo", "url")], stdout=dev_null, stderr=dev_null)
				subprocess.check_call(['git', 'fetch', 'statuscheck'], stdout=dev_null, stderr=dev_null)
				# get the hash of the specified branch
				requested_hash = subprocess.check_output(['git', 'rev-parse', "statuscheck/%s"%configParser.get(testtype+"_repo", "branch")], stderr=dev_null)
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
					subprocess.check_call(['git', 'checkout', "statuscheck/%s"%configParser.get(testtype+"_repo", "branch")], stdout=dev_null, stderr=dev_null)
					# Set the new remote to be 'origin'
					remotes = subprocess.check_output(['git', 'remote'], stderr=dev_null)
					if 'origin' in remotes:
						subprocess.check_call(['git', 'remote', 'rm', 'origin'], stdout=dev_null, stderr=dev_null)
					if 'statuscheck' in remotes:
						subprocess.check_call(['git', 'remote', 'rename', 'statuscheck', 'origin'], stdout=dev_null, stderr=dev_null)
					# Clean the build of the core we're trying to build
					print "   -- Running make clean CORE=%s"%configParser.get("building", "core")
					subprocess.check_call(['make', 'clean', "CORE=%s"%configParser.get("building", "core")], stdout=dev_null, stderr=dev_null)
				os.chdir(base_dir) # return to basedir in case not already there

			if ( world.build == "YES" ):
				# Build executable
				if need_to_build or not os.path.exists("%s/%s/%s"%(base_dir, testtype, world.executable)):
					print "Building " + testtype + " executable. "
					os.chdir("%s/%s"%(base_dir, testtype))
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
					os.chdir("%s"%(base_dir))

	print '----------------------------'
	print "/n" #}}}


@step('I perform a (\d+) processor MPAS "([^"]*)" run')#{{{
def run_mpas(step, procs, executable):

	if ( world.run == "YES" ):
		if executable.find("testing") >= 0:
			rundir = "%s/testing_tests/%s"%(world.basedir, world.test)
		elif executable.find("trusted") >= 0:
			rundir = "%s/trusted_tests/%s"%(world.basedir, world.test)

		os.chdir(rundir)
		command = "mpirun"
		arg1 = "-n"
		arg2 = "%s"%procs
		arg3 = "%s"%executable
		try:
			subprocess.check_call([command, arg1, arg2, arg3], stdout=dev_null, stderr=dev_null)  # check_call will throw an error if return code is not 0.
		except:
			os.chdir(world.basedir)  # return to basedir before err'ing.
			raise
		if os.path.exists('output.nc'):
			outfile = 'output.nc'
		else:
			outfile = "output.0000-01-01_00.00.00.nc"
		command = "mv"
		arg1 = outfile
		arg2 = "%sprocs.output.nc"%procs
		try:
			subprocess.check_call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)  # check_call will throw an error if return code is not 0.
		except:
			os.chdir(world.basedir)  # return to basedir before err'ing.
			raise
		if world.num_runs == 0:
			world.num_runs = 1
			world.run1 = "%s/%s"%(rundir, arg2)
			world.run1dir = rundir
			try:
				del world.rms_values
				world.rms_values = defaultdict(list)
			except:
				world.rms_values = defaultdict(list)
		elif world.num_runs == 1:
			world.num_runs = 2
			world.run2 = "%s/%s"%(rundir, arg2)
			world.run2dir = rundir
		os.chdir(world.basedir)#}}}

@step('I perform a (\d+) processor MPAS  "([^"]*)" run with restart')#{{{
def run_mpas_with_restart(step, procs, executable):

	if ( world.run == "YES" ):
		if executable.find("testing") >= 0:
			rundir = "%s/testing_tests/%s"%(world.basedir, world.test)
		elif executable.find("trusted") >= 0:
			rundir = "%s/trusted_tests/%s"%(world.basedir, world.test)

		os.chdir(rundir)

			#{{{ Setup initial namelist
		duration = seconds_to_timestamp(world.dt)
		final_time = seconds_to_timestamp(world.dt + 24*3600)

		namelistfile = open(world.namelist, 'r+')
		lines = namelistfile.readlines()
		namelistfile.seek(0)
		namelistfile.truncate()

		for line in lines:
			if line.find('config_start_time') >= 0:
				new_line = "    config_start_time = 'file'\n"
			elif line.find('config_run_duration') >= 0:
				new_line = "    config_run_duration = '%s'\n"%duration
			else:
				new_line = line

			namelistfile.write(new_line)

		namelistfile.close()
		del lines
			#}}}

		#{{{ Setup initial streams file
		tree = ET.parse(world.streams)
		root = tree.getroot()

		# Loop over immutable streams to find restart streams.
		for stream in root.findall('immutable_stream'):
			type = stream.get('type')

			if ( type.find("output") != -1 ):
				stream.set('output_interval', '01')

		# Loop over mutable streams to find restart and output streams
		for stream in root.findall('stream'):
			type = stream.get('type')
			name = stream.get('name')

			if ( type.find("output") != -1 ):
				stream.set('output_interval', '01')

			if ( name.find("output") != -1 ):
				stream.set('filename_template', 'output.nc')

		tree.write(world.streams)
		del tree
		del root
		#}}}

		command = "mpirun"
		arg1 = "-n"
		arg2 = "%s"%procs
		arg3 = "%s"%executable
		try:
			subprocess.check_call([command, arg1, arg2, arg3], stdout=dev_null, stderr=dev_null)  # check_call will throw an error if return code is not 0.
		except:
			os.chdir(world.basedir)  # return to basedir before err'ing.
			raise

		namelistfile = open(world.namelist, 'r+')
		lines = namelistfile.readlines()
		namelistfile.seek(0)
		namelistfile.truncate()

		for line in lines:
			if line.find('config_do_restart') >= 0:
				new_line = "    config_do_restart = .true.\n"
			else:
				new_line = line

			namelistfile.write(new_line)

		namelistfile.write("mv output.nc %sprocs.restarted.output.nc"%(procs))
		namelistfile.close()
		del lines

		command = "mpirun"
		arg1 = "-n"
		arg2 = "%s"%procs
		arg3 = "%s"%executable
		try:
			subprocess.check_call([command, arg1, arg2, arg3], stdout=dev_null, stderr=dev_null)
		except:
			os.chdir(world.basedir)  # return to basedir before err'ing.
			raise

		command = "mv"
		arg1 = "output.nc"
		arg2 = "%sprocs.restarted.output.nc"%procs
		try:
			subprocess.check_call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)
		except:
			os.chdir(world.basedir)  # return to basedir before err'ing.
			raise

		if world.num_runs == 0:
			world.num_runs = 1
			world.run1 = "%s/%s"%(rundir,arg2)
			world.run1dir = rundir
			try:
				del world.rms_values
				world.rms_values = defaultdict(list)
			except:
				world.rms_values = defaultdict(list)
		elif world.num_runs == 1:
			world.num_runs = 2
			world.run2 = "%s/%s"%(rundir,arg2)
			world.run2dir = rundir
		os.chdir(world.basedir)#}}}

@step('I compute the RMS of "([^"]*)"')#{{{
def compute_rms(step, variable):
	if ( world.run == "YES" ):
		if world.num_runs == 2:
			f1 = NetCDFFile("%s"%(world.run1),'r')
			f2 = NetCDFFile("%s"%(world.run2),'r')
			if len(f1.variables["%s"%variable].shape) == 3:
				field1 = f1.variables["%s"%variable][-1,:,:]
				field2 = f2.variables["%s"%variable][-1,:,:]
			elif len(f1.variables["%s"%variable].shape) == 2:
				field1 = f1.variables["%s"%variable][-1,:]
				field2 = f2.variables["%s"%variable][-1,:]
			else:
				assert False, "Unexpected number of dimensions in output file."

			field1 = field1 - field2
			field1 = field1 * field1
			rms = sum(field1)
			rms = rms / sum(field1.shape[:])
			rms = math.sqrt(rms)
			world.rms_values[variable].append(rms)
			f1.close()
			f2.close()
			os.chdir(world.basedir)
		else:
			print 'Less than two runs. Skipping RMS computation.'#}}}

@step('I see "([^"]*)" RMS of 0')#{{{
def check_rms_values(step, variable):
	if ( world.run ):
		if world.num_runs == 2:
			assert world.rms_values[variable][0] == 0.0, '%s RMS failed with value %s'%(variable, world.rms_values[variable][0])
		else:
			print 'Less than two runs. Skipping RMS check.'#}}}

@step('I clean the test directory')#{{{
def clean_test(step):
	if ( world.run ):
		command = "rm"
		arg1 = "-rf"
		arg2 = "%s/trusted_tests/%s"%(world.basedir,world.test)
		subprocess.call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)
		command = "rm"
		arg1 = "-rf"
		arg2 = "%s/testing_tests/%s"%(world.basedir,world.test)
		subprocess.call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)#}}}
