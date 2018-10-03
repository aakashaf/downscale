# script to bring the GIRR Radiation at top of Atmosphere through the clouds to generate 
def generate_nirr( cld_fn, girr_arr, output_filename ):
	'''
	generate nirr from girr and clouds for a common month

	* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
	** this is the c++ version given by Dave.  I am using R to calculate it here
	if (clds > -0.1) {
			nirr = cld.subset.v * (0.251 + (0.509*(1.0 - clds/100.0)))
		} else {
			nirr = -999.9; }
	* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

	'''
	with np.errstate( over='ignore' ):
		cld = rasterio.open( cld_fn )
		mask = cld.read_masks( 1 )
		cld_arr = cld.read( 1 )
		nirr_arr = girr_arr * ( 0.251 + ( 0.509 * ( 1.0 - cld_arr/100 ) ) )
		nirr_arr[ mask == 0 ] = cld.nodata

	meta = cld.meta
	meta.update( compress='lzw' )
	
	try:
		if not os.path.exists( os.path.dirname( output_filename ) ):
			os.makedirs( os.path.dirname( output_filename ) )
	except:
		pass

	with rasterio.open( output_filename, 'w', **meta ) as out:
		out.write( nirr_arr, 1 )
	return output_filename

if __name__ == '__main__':
	import os, glob, rasterio
	import numpy as np
	import pandas as pd
	from pathos.mp_map import mp_map

	# GLOBAL ARGS
	ncores = 64
	base_path = '/workspace/Shared/Tech_Projects/DeltaDownscaling/project_data'
	girr_dir = os.path.join( base_path, 'climatologies', 'other', '2km', 'girr' )

	# PREP INPUT FILES FOR PROCESSING
	girr = [ rasterio.open( i ).read( 1 ) for i in sorted( glob.glob( os.path.join( girr_dir, '*.tif' ) ) ) ]
	months = [ '01', '02', '03', '04', '05', '06', '07', '08', '09','10', '11', '12' ]
	girr = dict( zip( months, girr ) )

	# list the cloud files for a series
	# models = [ 'IPSL-CM5A-LR', 'GISS-E2-R', 'MRI-CGCM3', 'NCAR-CCSM4', 'GFDL-CM3', '5ModelAvg' ]
	models = [ 'CRU-TS40' ]
	variables = ['clt' ]
	# scenarios = [ 'historical', 'rcp26', 'rcp45', 'rcp60', 'rcp85' ]
	scenarios = [ 'historical' ]
	path_list = [ os.path.join( base_path, 'downscaled', model, scenario, variable, '*.tif' ) for model in models for variable in variables for scenario in scenarios ]

	for path in path_list:
		print( 'running: %s ' % path )
		clt = pd.Series( glob.glob( path ) )
		print( 'file count: %d' % len( clt ) )

		output_filenames = clt.apply( lambda x: x.replace('clt', 'rsds').replace( '_pct_', '_MJ-m2-d1_' ) ).tolist()
		month_grouper = clt.apply( lambda x: os.path.basename( x ).split( '.' )[0].split( '_' )[-2] )
		args_list = [ ( cltx, girr[ month ], out ) for cltx, out, month in zip( clt.tolist(), output_filenames, month_grouper ) ]

		# run it in parallel
		out = mp_map( lambda x: generate_nirr( *x ), args_list, nproc=ncores )
