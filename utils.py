import click
import os, subprocess, glob
from os.path import join
import time
from MethylationDataTypes import MethylationArray

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
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    input_dict=pickle.load(open(input_pkl,'rb'))
    methyl_array = MethylationArray(*extract_pheno_beta_df_from_pickle_dict(input_dict))
    methyl_array.merge_preprocess_sheet(pd.read_csv(input_formatted_sample_sheet,header=0))
    methyl_array.write_pickle(output_pkl)



if __name__ == '__main__':
    util()
