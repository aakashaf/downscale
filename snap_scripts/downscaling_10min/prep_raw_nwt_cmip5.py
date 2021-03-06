# PREPROCESS THE RAW CMIP5 OUTPUTS FROM ESGF INTO PREPPED NetCDF4 files for use in downscaling
# -- Built for the Northwest Territories (NWT) far-futures modeling project.
# Not a replacement for the standard preprocessor, just something to overcome the datetime issues
# in xarray/pandas where we cant deal with times >2200 without some severe issues.

import pandas as pd
import os

class Files( object ):
    def __init__( self, base_dir, *args, **kwargs ):
        '''
        list the files from the nested directory structure
        generated by SYNDA application and access of the ESGF CMIP5 data holdings
        '''
        self.base_dir = base_dir
        self.files = self.list_files( )
        self.df = self._to_dataframe( )

    def list_files( self ):
        return [ os.path.join( root, fn ) for root, subs, files in os.walk( self.base_dir ) \
                    if len( files ) > 0 for fn in files if fn.endswith( '.nc' ) ]
    @staticmethod
    def _split_fn( fn ):
        return os.path.basename( fn ).split( '.' )[0].split( '_' )
    @staticmethod
    def f( x ):
        '''
        take the files dataframe and split the years
        into begin year/month and end year/month and 
        add new columns to a new dataframe
        '''
        begin, end = x[ 'years' ].split( '-' )
        x['begin_month'] = begin[4:] 
        x['begin_year'] = begin[:4]
        x['end_month'] = end[4:]
        x['end_year'] = end[:4]
        return x
    def _to_dataframe( self ):
        import pandas as pd
        out = []
        for fn in self.files:
            variable, cmor_table, model, scenario, experiment, years = self._split_fn( fn )
            out.append( {'fn':fn, 'variable':variable, 'cmor_table':cmor_table, \
                        'model':model, 'scenario':scenario, 'experiment':experiment, 'years':years } )
            column_order = ['fn', 'variable', 'cmor_table', 'model', 'scenario', 'experiment', 'years']
        return pd.DataFrame( out, columns=column_order ).apply( self.f, axis=1 )

def get_slice_index( file_year_begin, file_year_end, desired_year_begin, desired_year_end ):
    years = np.repeat(range( file_year_begin, file_year_end+1 ), 12 ) # 12 is for 12 months
    year_min = min( years )

    if desired_year_begin < year_min:
        begin_idx = ( year_min - desired_year_begin )
    elif desired_year_begin > year_min:
        begin_idx = np.min( np.where(years == desired_year_begin) )

    begin_idx = (np.abs(years - desired_year_begin )).argmin()
    end_idx = (np.abs(years - desired_year_end )).argmin() + 12 # add 12 to get to the end of 12 months in the last year
    # end_idx = np.max( np.where( years == desired_year_end ) )
    return begin_idx, end_idx

def preprocess( filelist, begin_slice, end_slice, variable, output_filename ):
    # read in the existing dset
    ds = MFDataset( sorted( filelist ) )

    # build a new output dataset
    with Dataset( output_filename, 'w', format='NETCDF4_CLASSIC' ) as sub_ds:
        sub_ds.createDimension( 'lat', ds['lat'][:].shape[0] )
        lon = sub_ds.createDimension( 'lon', ds['lon'][:].shape[0] )
        time = sub_ds.createDimension( 'time', None )

        # Create coordinate variables for 4-dimensions
        times = sub_ds.createVariable('time', np.float64, ('time',))
        latitudes = sub_ds.createVariable('lat', np.float32,('lat',))
        longitudes = sub_ds.createVariable('lon', np.float32,('lon',))

        # Create the actual 3-d variable
        data = sub_ds.createVariable( variable, np.float32,('time','lat','lon') )

        # set the data
        times[:] = ds['time'][begin_slice:end_slice]
        latitudes[:] = ds['lat'][:]
        longitudes[:] = ds['lon'][:]
        data[:] = ds[variable][begin_slice:end_slice, ...].astype( np.float32 )

        # set up the global CF-convention-style meta attrs.
        sub_ds.setncatts( { k:getattr(ds, k) for k in ds.ncattrs() } )

        # local variable meta attrs...
        sub_ds[variable].setncatts( { k:getattr(ds[variable], k) for k in ds[variable].ncattrs() if not k.startswith('_')  } )

        # time attrs...
        sub_ds['time'].setncatts( { k:getattr(ds['time'], k) for k in ds['time'].ncattrs() } )

        # lon/lat attrs...
        sub_ds['lon'].setncatts( { k:getattr(ds['lon'], k) for k in ds['lon'].ncattrs() } )
        sub_ds['lat'].setncatts( { k:getattr(ds['lat'], k) for k in ds['lat'].ncattrs() } )

    return output_filename

if __name__ == '__main__':
    from netCDF4 import Dataset, MFDataset
    import numpy as np
    import itertools, glob, os
    # from downscale.preprocess import Preprocess

    # some setup args
    # base_dir = '/workspace/Shared/Tech_Projects/DeltaDownscaling/project_data/cmip5_nwt/data/cmip5'
    base_dir = '/workspace/Shared/Tech_Projects/DeltaDownscaling/project_data/cmip5_nwt_v2/cmip5_raw_restructure_V2'
    # prepped_dir = '/workspace/Shared/Tech_Projects/DeltaDownscaling/project_data/cmip5_nwt/data/prepped'
    prepped_dir = '/workspace/Shared/Tech_Projects/DeltaDownscaling/project_data/cmip5_nwt_v2/prepped'
    variables = [ 'tas', 'pr' ]
    scenarios = [ 'historical','rcp45', 'rcp60', 'rcp85' ]
    models = [ 'GFDL-CM3','IPSL-CM5A-LR','GISS-E2-R','CCSM4','MRI-CGCM3' ]

    if not os.path.exists( prepped_dir ):
        os.makedirs( prepped_dir )

    # lets get the darn data returned that we want:
    files_df = Files( base_dir )._to_dataframe( )
    log = open( os.path.join( prepped_dir, 'log_file_prep.txt' ), 'w' )
    out = []
    for variable, model, scenario in itertools.product( variables, models, scenarios ):
        print( 'running {}-{}-{}'.format( variable, model, scenario ) )
        # get the files we want to work with for this run
        cur_df = files_df[ (files_df.variable == variable) & (files_df.model == model) & (files_df.scenario == scenario) ].copy()
        cur_df = cur_df.apply( pd.to_numeric, errors='ignore' ) # dtypes updating
        cur_df = cur_df.sort_values(['end_year']) # sort it based on the end_year
        
        cur_files = cur_df['fn'].tolist()
        if len( cur_files ) > 0:
            if scenario == 'historical':
                years = (1850,2005)
            else:
                years = (2006,2300)

            # years = (2101,2300)
            raw_path = os.path.dirname( cur_files[0] )
            output_path = os.path.join( prepped_dir, model, scenario, variable )
            
            if not os.path.exists( output_path ):
                os.makedirs( output_path )

            experiment = 'r1i1p1'
            begin_time = str(years[0])
            end_time = str(years[1])
            print(cur_df.begin_year.min(), cur_df.end_year.max())
            
            try:
                output_filename = os.path.join( output_path, '_'.join([ variable, model, scenario, experiment, begin_time, str(cur_df.end_year.max()) ]) + '.nc' )
                begin_slice, end_slice = get_slice_index( cur_df.begin_year.min(), cur_df.end_year.max(), years[0], years[1] )
                out = out + [preprocess( cur_files, begin_slice, end_slice, variable, output_filename )]
            except:
                # log it 
                print( 'error : %s - %s - %s - %s - %s - %s \n\n' % (raw_path, variable, model, scenario, experiment, years) )
                log.write( 'error : %s - %s - %s - %s - %s - %s \n\n' % (raw_path, variable, model, scenario, experiment, years)  )
                pass
    log.flush()
    log.close()


# ::::TESTS::::
# files = [ os.path.join(r, fn) for r,s,files in os.walk( prepped_dir ) for fn in files if fn.endswith('.nc') ]
def test_file_length( fn ):
    '''
    [TEST] this test is to be sure that the filename begin/end
    years are in agreement with the number of files in the prepped NC.
    It (inadvertently) also tests that the variable names also in agreement 

    RETURNS:
    -------
    0 = no difference between the filename years and what live in the nc filename
    !=0 means there is something awry...

    error most likely means that the variable names dont match between the filename 
    and the file

    '''
    import xarray as xr
    begin, end = os.path.basename(fn).split('.')[0].split('_')[-2:]
    variable = os.path.basename(fn).split('.')[0].split('_')[0]
    ds = xr.open_dataset( fn, decode_times=False )
    ds[variable].shape[0]
    return len(range(int(begin), int(end)+1))*12 - ds[variable].shape[0]

# run test_file_length()
assert np.array([ test_file_length(fn) for fn in out ]).all() == 0

print( 'tests passed.' )
