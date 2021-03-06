def sort_files( files, split_on='_', elem_month=-2, elem_year=-1 ):
	'''
	sort a list of files properly using the month and year parsed
	from the filename.  This is useful with SNAP data since the standard
	is to name files like '<prefix>_MM_YYYY.tif'.  If sorted using base
	Pythons sort/sorted functions, things will be sorted by the first char
	of the month, which makes thing go 1, 11, ... which sucks for timeseries
	this sorts it properly following SNAP standards as the default settings.

	ARGUMENTS:
	----------
	files = [list] list of `str` pathnames to be sorted by month and year. usually from glob.glob.
	split_on = [str] `str` character to split the filename on.  default:'_', SNAP standard.
	elem_month = [int] slice element from resultant split filename list.  Follows Python slicing syntax.
		default:-2. For SNAP standard.
	elem_year = [int] slice element from resultant split filename list.  Follows Python slicing syntax.
		default:-1. For SNAP standard.

	RETURNS:
	--------
	sorted `list` by month and year ascending. 

	'''
	import pandas as pd
	months = [ int(fn.split('.')[0].split( split_on )[elem_month]) for fn in files ]
	years = [ int(fn.split('.')[0].split( split_on )[elem_year]) for fn in files ]
	df = pd.DataFrame( {'fn':files, 'month':months, 'year':years} )
	df_sorted = df.sort_values( ['year', 'month' ] )
	return df_sorted.fn.tolist()

def only_years( files, begin=1901, end=2100, split_on='_', elem_year=-1 ):
	'''
	return new list of filenames where they are truncated to begin:end

	ARGUMENTS:
	----------
	files = [list] list of `str` pathnames to be sorted by month and year. usually from glob.glob.
	begin = [int] four digit integer year of the begin time default:1901
	end = [int] four digit integer year of the end time default:2100
	split_on = [str] `str` character to split the filename on.  default:'_', SNAP standard.
	elem_year = [int] slice element from resultant split filename list.  Follows Python slicing syntax.
		default:-1. For SNAP standard.

	RETURNS:
	--------
	sliced `list` to begin and end year.
	'''
	import pandas as pd
	years = [ int(fn.split('.')[0].split( split_on )[elem_year]) for fn in files ]
	df = pd.DataFrame( { 'fn':files, 'year':years } )
	df_slice = df[ (df.year >= begin ) & (df.year <= end ) ]
	return df_slice.fn.tolist()

def get_month_seaon( fn ):
	# seasons
	seasonal_lookup = { 1:'DJF', 2:'DJF', 3:'MAM', 4:'MAM', 5:'MAM', \
						6:'JJA', 7:'JJA', 8:'JJA',\
						 9:'SON', 10:'SON', 11:'SON', 12:'DJF' }

	fn = os.path.basename( fn )
	month, year = fn.replace( '.tif', '' ).split( '_' )[-2:]
	return seasonal_lookup[ int(month) ]

def get_year( fn ):
	fn = os.path.basename( fn )
	month, year = fn.replace( '.tif', '' ).split( '_' )[-2:]
	return year

def read_raster( fn, band=1 ):
	'''
	clean way to open / read and properly close a GTiff
	'''
	import rasterio
	with rasterio.open( fn ) as out:
		arr = out.read( band )
	return arr

def calc_seasonal_mean( season_name, files, output_path, agg_metric='mean', *args, **kwargs ):
	'''
	calculate seasonal means
	'''
	years = [ int( get_year( fn ) ) for fn in files ]
	year = str( max( years ) )
	fn = files[0]
	rst = rasterio.open( fn )
	mask = rst.read_masks( 1 )
	meta = rst.meta
	
	if 'transform' in meta.keys():
		meta.pop( 'transform' )

	meta.update( compress='lzw' )

	metric_switch = { 'mean':np.mean, 'total':np.sum, 'min':np.min, 'max':np.max }
	variable, metric, units, project, model, scenario = os.path.basename( fn ).split( '.' )[0].split( '_' )[:-2]
	arr = metric_switch[ agg_metric ]( [ read_raster( i ) for i in files ], axis=0 )

	arr[ mask == 0 ] = meta[ 'nodata' ]

	output_filename = os.path.join( output_path, model, scenario, variable, '_'.join([ variable, agg_metric, units, project, model, scenario, season_name, year]) + '.tif' )

	dirname = os.path.dirname( output_filename )
	try:
		if not os.path.exists( dirname ):
			os.makedirs( dirname )
	except:
		pass

	with rasterio.open( output_filename, 'w', **meta ) as out:
		out.write( arr, 1 )

	return output_filename

def wrap( x ):
	''' 
	multiprocessing wrapper for clean 
	argument handling without lambda 
	'''
	return calc_seasonal_mean( *x )

def make_seasonals( base_path, output_path, model, scenario, variable, begin, end, ncpus ):
	'''
	function to calculate and output mean seasonal monthly data across decades
	
	ARGUMENTS:
	----------
	base_path = [  ]  
	output_path = [  ]  
	model = [  ]  
	scenario = [  ]  
	variable = [  ]  
	begin = [  ]  
	end = [  ]  
	ncpus = [  ]  

	RETURNS
	-------
	output_directory of newly produced GeoTiffs if successful. else, error.

	'''
	# modeled data
	files = glob.glob( os.path.join( base_path, model, scenario, variable, '*.tif' ) )
	files = sort_files( only_years( files, begin=begin, end=end, split_on='_', elem_year=-1 ) )

	season_names = [ get_month_seaon( fn ) for fn in files ]
	years = [ int(get_year( fn )) for fn in files ]

	# min / max years
	start_year =  str( min(years) )
	end_year = str( max(years) )

	# drop data for start_year JF and end_year D
	files = [ fn for fn in files if not '_'.join([ '01',start_year ]) in fn if not '_'.join([ '02',start_year ]) in fn if not '_'.join([ '12',end_year ]) in fn ]
	files = pd.Series( files )
	
	split_n = len( files ) / 3
	grouped_seasons = np.split( np.array( files ), split_n )
	season_names = [ get_month_seaon( i[0] ) for i in grouped_seasons ]

	seasons = zip( season_names, grouped_seasons )

	args = [ ( season_name, file_group, output_path ) for season_name, file_group in seasons ]
	
	pool = mp.Pool( ncpus )
	out = pool.map( lambda x: wrap( x ), args )
	pool.close()
	pool.join()
	pool.terminate()
	pool = None
	return output_path

if __name__ == '__main__':
	import os, glob, itertools, rasterio
	import xarray as xr
	import pandas as pd
	import numpy as np
	from pathos import multiprocessing as mp
	import argparse

	'''
	this tool assumes that the data are stored in a directory structure as follows:
	
	base_path
		model
			scenario
				variable
					FILES
	'''

	# parse the commandline arguments
	parser = argparse.ArgumentParser( description='downscale the AR5-CMIP5 data to the AKCAN extent required by SNAP' )
	parser.add_argument( "-b", "--base_path", action='store', dest='base_path', type=str, help="path to the directory where the downscaled modeled data are stored" )
	parser.add_argument( "-o", "--output_path", action='store', dest='output_path', type=str, help="path to the output directory" )
	parser.add_argument( "-m", "--model", action='store', dest='model', type=str, help="model name (exact)" )
	parser.add_argument( "-s", "--scenario", action='store', dest='scenario', type=str, help="scenario name (exact)" )
	parser.add_argument( "-p", "--project", action='store', dest='project', type=str, help="project name (exact)" )
	parser.add_argument( "-v", "--variable", action='store', dest='variable', type=str, help="cmip5 variable name (exact)" )
	parser.add_argument( "-am", "--agg_metric", action='store', dest='agg_metric', type=str, help="string name of the metric to compute the decadal summary - mean, max, min, total" )
	parser.add_argument( "-nc", "--ncpus", action='store', dest='ncpus', type=int, help="number of cpus to use in multiprocessing" )	
	args = parser.parse_args()

	# unpack for cleaner var access:
	base_path = args.base_path
	output_path = args.output_path
	model = args.model
	scenario = args.scenario
	project = args.project
	variable = args.variable
	ncpus = args.ncpus
	agg_metric = args.agg_metric

	# switches to deal with different date groups.  Hardwired to CMIP5 and CRU TS323 currently.
	cmip_switch = { 'historical':(1900,2005), 'rcp26':(2005,2100), 'rcp45':(2005,2100), 'rcp60':(2005,2100), 'rcp85':(2006,2100) }
	cru_switch = { 'historical':(1901,2014) }
	project_switch = { 'cmip5':cmip_switch, 'cru':cru_switch }

	begin, end = project_switch[ project ][ scenario ]

	print( 'running: {} {} {}'.format( model, scenario, variable ) )
	_ = make_seasonals( base_path, output_path, model, scenario, variable, begin, end, ncpus )



# # # # EXAMPLE RUN # # # # 
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # FOR TESTING THEN REMOVE
# setup args
# import subprocess, os
# base_path = '/workspace/Shared/Tech_Projects/EPSCoR_Southcentral/project_data/downscaled_cru_clipped'
# output_path = '/workspace/Shared/Tech_Projects/EPSCoR_Southcentral/project_data/derived_outputs/monthly_decadals'
# ncpus = 32
# project = 'cru' # 'cmip5'
# variables = [ 'tasmin', 'tasmax', 'tas', 'pr' ]
# models = [ 'ts323' ] # [ 'IPSL-CM5A-LR', 'MRI-CGCM3', 'GISS-E2-R', 'GFDL-CM3', 'CCSM4', '5ModelAvg' ] # 
# scenarios = [ 'historical'] # [ 'historical', 'rcp26', 'rcp45', 'rcp60', 'rcp85' ] # [ 'historical' ]

# for model in models:
# 	for scenario in scenarios:
# 		for variable in variables:
# 			agg_metric = 'mean'
# 			# if variable == 'pr':
# 			# 	agg_metric = 'total'
# 			# else:
# 			# 	agg_metric = 'mean'
# 			os.chdir( '/workspace/UA/malindgren/repos/downscale/snap_scripts' )
# 			command = ' '.join([ 'ipython', 'compute_decadal_grids_epscor_se.py', '--', '-b', base_path, '-o ', output_path, '-m ', model , '-s', scenario, '-p', project, '-v', variable ,'-am', agg_metric ,'-nc', str(ncpus) ])
# 			os.system( command )

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 




# some setup
base_path = '/workspace/Shared/Tech_Projects/EPSCoR_Southcentral/project_data/downscaled_cmip5_clipped'
output_path = '/workspace/Shared/Tech_Projects/EPSCoR_Southcentral/project_data/derived_outputs/seasonal_annuals'
project = 'cmip5'
models = [ 'IPSL-CM5A-LR', 'MRI-CGCM3', 'GISS-E2-R', 'GFDL-CM3', 'CCSM4', '5ModelAvg' ]
scenarios = [ 'historical', 'rcp26', 'rcp45', 'rcp60', 'rcp85' ]
variables = [ 'tasmin', 'tasmax', 'pr', 'tas' ]
ncpus = 32


# run all combinations
for model, scenario, variable in itertools.product( models, scenarios, variables ):
	print( 'running: {} {} {}'.format( model, scenario, variable ) )
	begin, end = project_switch[ project ][ scenario ]

	_ = main( base_path, output_path, model, scenario, variable, begin, end, ncpus )

