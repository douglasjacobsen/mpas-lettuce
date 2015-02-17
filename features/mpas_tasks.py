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
	return timestamp
#}}}

@step('I perform a (\d+) processor MPAS "([^"]*)" run')#{{{
def run_mpas(step, procs, executable):

	if ( world.run == True ):
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
		os.chdir(world.basedir)
#}}}

@step('I perform a (\d+) processor MPAS  "([^"]*)" run with restart')#{{{
def run_mpas_with_restart(step, procs, executable):

	if ( world.run == True ):
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
				new_line = "	config_start_time = 'file'\n"
			elif line.find('config_run_duration') >= 0:
				new_line = "	config_run_duration = '%s'\n"%duration
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
				new_line = "	config_do_restart = .true.\n"
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
		os.chdir(world.basedir)
#}}}

@step('I compute the RMS of "([^"]*)"')#{{{
def compute_rms(step, variable):
	if ( world.run == True ):
		if world.num_runs == 2:
			f1 = NetCDFFile("%s"%(world.run1),'r')
			f2 = NetCDFFile("%s"%(world.run2),'r')
			if len(f1.dimensions['Time']) == 1:
				timeindex = 0
			else:
				timeindex = -1
			if len(f1.variables["%s"%variable].shape) == 3:
				field1 = f1.variables["%s"%variable][timeindex,:,:]
				field2 = f2.variables["%s"%variable][timeindex,:,:]
			elif len(f1.variables["%s"%variable].shape) == 2:
				field1 = f1.variables["%s"%variable][timeindex,:]
				field2 = f2.variables["%s"%variable][timeindex,:]
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
			print 'Less than two runs. Skipping RMS computation.'
#}}}

@step('I see "([^"]*)" RMS of 0')#{{{
def check_rms_values(step, variable):
	if ( world.run ):
		if world.num_runs == 2:
			assert world.rms_values[variable][0] == 0.0, '%s RMS failed with value %s'%(variable, world.rms_values[variable][0])
		else:
			print 'Less than two runs. Skipping RMS check.'
#}}}

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
		subprocess.call([command, arg1, arg2], stdout=dev_null, stderr=dev_null)
#}}}
