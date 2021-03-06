# # # # # # # # # # # # # # 
# # convert tas/hur to vap
# # # # # # # # # # # # # # 

def convert_to_vap( tas_arr, hur_arr ):
	''' create relative humidity from the CRU tas / vap '''
	esa_arr = 6.112 * np.exp( 17.62 * tas_arr/ (243.12 + tas_arr) )
	# esa_arr = 6.112 * np.exp( 22.46 * tas_arr / (272.62 + tas_arr) )
	return (hur_arr*esa_arr)/100

def make_vap( hur_fn, tas_fn, out_fn ):
	''' make vapor pressure from hur and tas.'''
	hur = rasterio.open( hur_fn )
	tas = rasterio.open( tas_fn )

	hur_arr = hur.read( 1 )
	tas_arr = tas.read( 1 )
	mask = hur.read_masks( 1 )

	with np.errstate( all='ignore' ):
		vap_arr = convert_to_vap( tas_arr, hur_arr )
		
	# vap_arr[ mask == 0 ] = hur.nodata
	vap_arr = np.around( vap_arr, 2 ) # roundit
	vap_arr[ mask == 0 ] = hur.nodata # reset mask

	dirname, basename = os.path.split( out_fn )
	try:
		if not os.path.exists( dirname ):
			os.makedirs( dirname )
	except:
		pass 

	meta = hur.meta
	meta.update( compress='lzw' )
	
	with rasterio.open( output_filename, 'w', **meta ) as out:
		out.write( vap_arr, 1 )

	return output_filename

def wrap_make_vap( x ):
	''' runner for multiprocessing '''
	return make_vap( *x )

if __name__ == '__main__':
	import os, rasterio, itertools, functools, glob
	import numpy as np
	from pathos.mp_map import mp_map

	# # vars
	base_dir = '/workspace/Shared/Tech_Projects/DeltaDownscaling/project_data/downscaled'
	
	# list ALL relative humidity
	hur_files = [ os.path.join(r,fn) for r,s,files in os.walk( base_dir ) for fn in files if fn.endswith( '.tif' ) and 'hur_' in fn ]

	# since the pathing is the same except for variable, metric, units we can just change the list to make a tas list
	tas_files = [ fn.replace('/hur','/tas').replace('mean_pct','mean_C') for fn in hur_files ]

	# make the output files from one of the lists
	output_filenames = [ fn.replace('/hur','/vap').replace('mean_pct','mean_hPa') for fn in hur_files ]

	args = zip( hur_files, tas_files, output_filenames )
	out = mp_map( wrap_make_vap, files, nproc=64 )
