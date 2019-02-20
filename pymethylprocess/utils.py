import click
import os, subprocess, glob
from os.path import join
import time
from pymethylprocess.MethylationDataTypes import MethylationArray

CONTEXT_SETTINGS = dict(help_option_names=['-h','--help'], max_content_width=90)

@click.group(context_settings= CONTEXT_SETTINGS)
@click.version_option(version='0.1')
def util():
    pass

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./train_val_test_sets/', help='Output directory for training, testing, and validation sets.', type=click.Path(exists=False), show_default=True)
@click.option('-tp', '--train_percent', default=0.8, help='Percent data training on.', show_default=True)
@click.option('-vp', '--val_percent', default=0.1, help='Percent of training data that comprises validation set.', show_default=True)
@click.option('-cat', '--categorical', is_flag=True, help='Multi-class prediction.', show_default=True)
@click.option('-do', '--disease_only', is_flag=True, help='Only look at disease, or text before subtype_delimiter.')
@click.option('-k', '--key', default='disease', help='Key to split on.', type=click.Path(exists=False), show_default=True)
@click.option('-sd', '--subtype_delimiter', default=',', help='Delimiter for disease extraction.', type=click.Path(exists=False), show_default=True)
def train_test_val_split(input_pkl,output_dir,train_percent,val_percent, categorical, disease_only, key, subtype_delimiter):
    os.makedirs(output_dir,exist_ok=True)
    methyl_array = MethylationArray.from_pickle(input_pkl)
    train_arr, test_arr, val_arr = methyl_array.split_train_test(train_percent, categorical, disease_only, key, subtype_delimiter, val_percent)
    train_arr.write_pickle(join(output_dir,'train_methyl_array.pkl'))
    test_arr.write_pickle(join(output_dir,'test_methyl_array.pkl'))
    val_arr.write_pickle(join(output_dir,'val_methyl_array.pkl'))

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-k', '--key', default='disease', help='Key to split on.', type=click.Path(exists=False), show_default=True)
def counts(input_pkl,key):
    if input_pkl.endswith('.pkl'):
        MethylationArray.from_pickle(input_pkl).categorical_breakdown(key)
    else:
        for input_pkl in glob.glob(join(input_pkl,'*.pkl')):
            print(input_pkl)
            MethylationArray.from_pickle(input_pkl).categorical_breakdown(key)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def print_shape(input_pkl):
    print(MethylationArray.from_pickle(input_pkl).beta.shape)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-k', '--key', default='disease', help='Key to split on.', type=click.Path(exists=False), show_default=True)
@click.option('-d', '--disease_only', is_flag=True, help='Only look at disease, or text before subtype_delimiter.')
@click.option('-sd', '--subtype_delimiter', default=',', help='Delimiter for disease extraction.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./fixed_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def fix_key(input_pkl,key,disease_only,subtype_delimiter,output_pkl):
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    methyl_array=MethylationArray.from_pickle(input_pkl)
    methyl_array.remove_whitespace(key)
    if disease_only:
        methyl_array.split_key(key, subtype_delimiter)
    methyl_array.write_pickle(output_pkl)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-k', '--key', default='disease', help='Key to split on.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./stratified/', help='Output directory for stratified.', type=click.Path(exists=False), show_default=True)
def stratify(input_pkl,key,output_dir):
    for name, methyl_array in MethylationArray.from_pickle(input_pkl).groupby(key):
        out_dir=os.path.join(output_dir,name.replace('/','-').replace(' ',''))
        os.makedirs(out_dir,exist_ok=True)
        methyl_array.write_pickle(os.path.join(out_dir,'methyl_array.pkl'))

@util.command()
@click.option('-i', '--input_pkl', default='./preprocess_outputs/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./autosomal/methyl_array.pkl', help='Output methyl array autosomal.', type=click.Path(exists=False), show_default=True)
@click.option('-a', '--array_type', default='450k', help='Array Type.', type=click.Choice(['450k','850k']), show_default=True)
def remove_sex(input_pkl,output_pkl, array_type):
    import numpy as np
    #from rpy2.robjects import pandas2ri
    from pymethylprocess.meffil_functions import r_autosomal_cpgs
    #pandas2ri.activate()
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    autosomal_cpgs = r_autosomal_cpgs(array_type)#pandas2ri.ri2py()
    methyl_array=MethylationArray.from_pickle(input_pkl)
    methyl_array.beta = methyl_array.beta.loc[:,np.intersect1d(list(methyl_array.beta),autosomal_cpgs)]
    methyl_array.write_pickle(output_pkl)

@util.command()
@click.option('-ro', '--input_r_object_dir', default='./preprocess_outputs/', help='Input directory containing qc data.', type=click.Path(exists=False), show_default=True)
@click.option('-a', '--algorithm', default='meffil', help='Algorithm to run cell type.', type=click.Choice(['meffil','minfi']), show_default=True)
@click.option('-ref', '--reference', default='cord blood gse68456', help='Cell Type Reference.', type=click.Choice(['andrews and bakulski cord blood','blood gse35069', 'blood gse35069 chen', 'blood gse35069 complete', 'cord blood gse68456', 'gervin and lyle cord blood', 'saliva gse48472']), show_default=True)
@click.option('-o', '--output_csv', default='./added_cell_counts/cell_type_estimates.csv', help='Output cell type estimates.', type=click.Path(exists=False), show_default=True)
def ref_estimate_cell_counts(input_r_object_dir, algorithm, reference, output_csv):
    import rpy2.robjects as robjects
    from rpy2.robjects import pandas2ri, numpy2ri
    pandas2ri.activate()
    from pymethylprocess.meffil_functions import est_cell_counts_meffil, est_cell_counts_minfi
    os.makedirs(output_csv[:output_csv.rfind('/')],exist_ok=True)
    read_r_object = robjects.r('readRDS')
    robjects.r('library({})'.format(algorithm))
    if algorithm == 'meffil':
        qc_list = read_r_object(join(input_r_object_dir,'QCObjects.rds'))
        cell_counts = est_cell_counts_meffil(qc_list,reference)
    else:
        rgset = read_r_object(join(input_r_object_dir,'RGSet.rds'))
        cell_counts = est_cell_counts_minfi(rgset)
    # find where samples intersect
    pandas2ri.ri2py(robjects.r('as.data.frame')(robjects.r('as.table')(cell_counts))).to_csv(output_csv)

@util.command()
@click.option('-i', '--input_pkl', default='./autosomal/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./no_snp/methyl_array.pkl', help='Output methyl array autosomal.', type=click.Path(exists=False), show_default=True)
@click.option('-a', '--array_type', default='450k', help='Array Type.', type=click.Choice(['450k','850k']), show_default=True)
def remove_snps(input_pkl,output_pkl, array_type):
    import numpy as np
    #from rpy2.robjects import pandas2ri
    from pymethylprocess.meffil_functions import r_snp_cpgs
    #pandas2ri.activate()
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    snp_cpgs = r_snp_cpgs(array_type)#pandas2ri.ri2py()
    methyl_array=MethylationArray.from_pickle(input_pkl)
    methyl_array.beta = methyl_array.beta.loc[:,np.setdiff1d(list(methyl_array.beta),snp_cpgs)]
    methyl_array.write_pickle(output_pkl)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-a', '--array_type', default='450k', help='Array Type.', type=click.Choice(['450k','850k']), show_default=True)
def print_number_sex_cpgs(input_pkl,array_type):
    import numpy as np
    #from rpy2.robjects import pandas2ri
    from pymethylprocess.meffil_functions import r_autosomal_cpgs
    #pandas2ri.activate()
    autosomal_cpgs = r_autosomal_cpgs(array_type)#pandas2ri.ri2py()
    methyl_array=MethylationArray.from_pickle(input_pkl)
    n_autosomal = len(np.intersect1d(list(methyl_array.beta),autosomal_cpgs))
    n_cpgs = len(list(methyl_array.beta))
    n_sex = n_cpgs - n_autosomal
    percent_sex = round(float(n_sex)/n_cpgs,2)
    print("There are {} autosomal cpgs in your methyl array and {} sex cpgs. Sex CpGs make up {}\% of {} total cpgs.".format(n_autosomal,n_sex,percent_sex,n_cpgs))

@util.command()
@click.option('-i', '--input_pkl_dir', default='./train_val_test_sets/', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./train_val_test_sets_fs/', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-n', '--n_top_cpgs', default=300000, help='Number cpgs to include with highest variance across population.', show_default=True)
@click.option('-f', '--feature_selection_method', default='mad', type=click.Choice(['mad','spectral']))
@click.option('-mm', '--metric', default='correlation', type=click.Choice(['euclidean','cosine','correlation']))
@click.option('-nn', '--n_neighbors', default=0, help='Number neighbors for feature selection, default enacts rbf kernel.', show_default=True)
@click.option('-m', '--mad_top_cpgs', default=0, help='Number cpgs to apply mad filtering first before more sophisticated feature selection. If 0 or primary feature selection is mad, no mad pre-filtering.', show_default=True)
def feature_select_train_val_test(input_pkl_dir,output_dir,n_top_cpgs=300000, feature_selection_method='mad', metric='correlation', n_neighbors=10, mad_top_cpgs=0):
    """Filter CpGs by taking x top CpGs with highest mean absolute deviation scores or via spectral feature selection."""
    os.makedirs(output_dir,exist_ok=True)
    train_pkl,val_pkl,test_pkl = join(input_pkl_dir,'train_methyl_array.pkl'), join(input_pkl_dir,'val_methyl_array.pkl'), join(input_pkl_dir,'test_methyl_array.pkl')
    train_methyl_array, val_methyl_array, test_methyl_array = MethylationArray.from_pickle(train_pkl), MethylationArray.from_pickle(val_pkl), MethylationArray.from_pickle(test_pkl)

    methyl_array = MethylationArrays([train_methyl_array,val_methyl_array]).combine()

    if mad_top_cpgs and feature_selection_method != 'mad':
        methyl_array.feature_select(mad_top_cpgs,'mad')

    methyl_array.feature_select(n_top_cpgs,feature_selection_method, metric, nn=n_neighbors)

    cpgs = methyl_array.return_cpgs()

    train_arr.subset_cpgs(cpgs).write_pickle(join(output_dir,'train_methyl_array.pkl'))
    test_arr.subset_cpgs(cpgs).write_pickle(join(output_dir,'test_methyl_array.pkl'))
    val_arr.subset_cpgs(cpgs).write_pickle(join(output_dir,'val_methyl_array.pkl'))

### MISC

@util.command()
@click.option('-i', '--input_dir', default='./', help='Directory containing jpg.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./preprocess_output_images/', help='Output directory for images.', type=click.Path(exists=False), show_default=True)
def move_jpg(input_dir, output_dir):
    """Move preprocessing jpegs to preprocessing output directory."""
    os.makedirs(output_dir, exist_ok=True)
    subprocess.call('mv {} {}'.format(os.path.join(input_dir,'*.jpg'),os.path.abspath(output_dir)),shell=True)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./backup/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def backup_pkl(input_pkl, output_pkl):
    """Copy methylarray pickle to new location to backup."""
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    subprocess.call('rsync {} {}'.format(input_pkl, output_pkl),shell=True)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./final_preprocessed/', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def pkl_to_csv(input_pkl, output_dir):
    """Output methylarray pickle to csv."""
    os.makedirs(output_dir,exist_ok=True)
    input_dict=pickle.load(open(input_pkl,'rb'))
    for k in input_dict.keys():
        input_dict[k].to_csv('{}/{}.csv'.format(output_dir,k))

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-is', '--input_formatted_sample_sheet', default='./tcga_idats/minfi_sheet.csv', help='Information passed through function create_sample_sheet, has Basename and disease fields.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./modified_processed/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def modify_pheno_data(input_pkl,input_formatted_sample_sheet,output_pkl):
    """Use another spreadsheet to add more descriptive data to methylarray."""
    import pandas as pd
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    methyl_array = MethylationArray.from_pickle(input_pkl)
    methyl_array.merge_preprocess_sheet(pd.read_csv(input_formatted_sample_sheet,header=0))
    methyl_array.write_pickle(output_pkl)

@util.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-is', '--input_formatted_sample_sheet', default='./tcga_idats/minfi_sheet.csv', help='Information passed through function create_sample_sheet, has Basename and disease fields.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./modified_processed/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-c', '--index_col', default=0, help='Index col when reading csv.', show_default=True)
def overwrite_pheno_data(input_pkl,input_formatted_sample_sheet,output_pkl,index_col):
    """Use another spreadsheet to add more descriptive data to methylarray."""
    import pandas as pd
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    methyl_array = MethylationArray.from_pickle(input_pkl)
    methyl_array.overwrite_pheno_data(pd.read_csv(input_formatted_sample_sheet,index_col=(index_col if index_col!=-1 else None),header=0))
    methyl_array.write_pickle(output_pkl)

if __name__ == '__main__':
    util()