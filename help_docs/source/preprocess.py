import rpy2.robjects as robjects
from rpy2.robjects.packages import importr
import rpy2.interactive as r
import rpy2.robjects.packages as rpackages
import os, subprocess
import click
import glob
import numpy as np, pandas as pd
from collections import Counter
#import impyute
from functools import reduce
from rpy2.robjects import pandas2ri, numpy2ri
import sqlite3
import pickle
pandas2ri.activate()
numpy2ri.activate()

CONTEXT_SETTINGS = dict(help_option_names=['-h','--help'], max_content_width=90)

@click.group(context_settings= CONTEXT_SETTINGS)
@click.version_option(version='0.1')
def preprocess():
    pass

class TCGADownloader:
    def __init__(self):
        pass

    def download_tcga(self, output_dir):
        tcga = importr("TCGAbiolinks")
        print(tcga)
        robjects.r("""
                   library(TCGAbiolinks)
                   projects <- TCGAbiolinks:::getGDCprojects()$project_id
                   projects <- projects[grepl('^TCGA',projects,perl=T)]
                   match.file.cases.all <- NULL
                   for(proj in projects){
                        print(proj)
                        query <- GDCquery(project = proj,
                                          data.category = "Raw microarray data",
                                          data.type = "Raw intensities",
                                          experimental.strategy = "Methylation array",
                                          legacy = TRUE,
                                          file.type = ".idat",
                                          platform = "Illumina Human Methylation 450")
                        match.file.cases <- getResults(query,cols=c("cases","file_name"))
                        match.file.cases$project <- proj
                        match.file.cases.all <- rbind(match.file.cases.all,match.file.cases)
                        tryCatch(GDCdownload(query, method = "api", files.per.chunk = 20),
                                 error = function(e) GDCdownload(query, method = "client"))
                    }
                    # This will create a map between idat file name, cases (barcode) and project
                    readr::write_tsv(match.file.cases.all, path = "idat_filename_case.txt")
                    # code to move all files to local folder
                    for(file in dir(".",pattern = ".idat", recursive = T)){
                        TCGAbiolinks:::move(file,file.path('%s',basename(file)))
                    }
                   """%output_dir)

    def download_clinical(self, output_dir):
        robjects.r("""
                   library(TCGAbiolinks)
                   library(data.table)
                   projects <- TCGAbiolinks:::getGDCprojects()$project_id
                   projects <- projects[grepl('^TCGA',projects,perl=T)]
                   match.file.cases.all <- NULL
                   data <- list()
                   for(n in 1:length(projects)){
                        proj <- projects[n]
                        clin.query <- GDCquery_clinic(project = proj,
                                          type='clinical', save.csv=F)
                        data[[length(data)+1]] = clin.query
                    }
                    df <- rbindlist(data)
                    write.csv(df, file=file.path('%s','clinical_info.csv'))
                   """%output_dir)

    def download_geo(self, query, output_dir):
        base=importr('base')
        geo = importr("GEOquery")
        geo.getGEOSuppFiles(query)
        tar_path=os.popen('conda list | grep "packages in environment at" | awk "{print $6}"').read().split()[-1].replace(':','')+'/bin/tar'
        if not os.path.exists(tar_path):
            tar_path = 'internal'
        robjects.r["untar"]("{0}/{0}_RAW.tar".format(query), exdir = "{}/idat".format(query), tar=tar_path)
        idatFiles = robjects.r('list.files("{}/idat", pattern = "idat.gz$", full = TRUE)'.format(query))
        robjects.r["sapply"](idatFiles, robjects.r["gunzip"], overwrite = True)
        subprocess.call('mv {}/idat/*.idat {}/'.format(query, output_dir),shell=True)
        pandas2ri.ri2py(robjects.r['as'](robjects.r("phenoData(getGEO('{}')[[1]])".format(query)),'data.frame')).to_csv('{}/{}_clinical_info.csv'.format(output_dir,query))# ,GSEMatrix = FALSE


class PreProcessPhenoData:
    def __init__(self, pheno_sheet, idat_dir, header_line=0):
        self.xlsx = True if pheno_sheet.endswith('.xlsx') or pheno_sheet.endswith('.xls') else False
        if self.xlsx:
            self.pheno_sheet = pd.read_excel(pheno_sheet,header=header_line)
        else:
            self.pheno_sheet = pd.read_csv(pheno_sheet, header=header_line)
        self.idat_dir = idat_dir

    def format_geo(self, disease_class_column="methylation class:ch1", include_columns={}):
        idats = glob.glob("{}/*.idat".format(self.idat_dir))
        idat_basenames = np.unique(np.vectorize(lambda x: '_'.join(x.split('/')[-1].split('_')[:3]))(idats))
        idat_geo_map = dict(zip(np.vectorize(lambda x: x.split('_')[0])(idat_basenames),np.array(idat_basenames)))
        self.pheno_sheet['Basename'] = self.pheno_sheet['geo_accession'].map(idat_geo_map)
        self.pheno_sheet = self.pheno_sheet[self.pheno_sheet['Basename'].isin(idat_basenames)]
        self.pheno_sheet.loc[:,'Basename'] = self.pheno_sheet['Basename'].map(lambda x: self.idat_dir+x)
        col_dict = {'geo_accession':'AccNum',disease_class_column:'disease'}
        col_dict.update(include_columns)
        self.pheno_sheet = self.pheno_sheet[['Basename', 'geo_accession',disease_class_column]+(list(include_columns.keys()) if include_columns else [])].rename(columns=col_dict)

    def format_tcga(self, mapping_file="idat_filename_case.txt"):
        def decide_case_control(barcode):
            case_control_num = int(barcode.split('-')[3][:2])
            if case_control_num < 10:
                return 'case'
            elif case_control_num < 20:
                return 'normal'
            else:
                return 'control'
            return 0
        idats = glob.glob("{}/*.idat".format(self.idat_dir))
        barcode_mappings = pd.read_csv(mapping_file,sep='\t')
        barcode_mappings['barcodes'] = np.vectorize(lambda x: '-'.join(x.split('-')[:3]))(barcode_mappings['cases'])
        barcode_mappings['idats'] = barcode_mappings['file_name'].map(lambda x: x[:x.rfind('_')])
        barcode_mappings_d1 = dict(barcode_mappings[['barcodes','idats']].values.tolist())
        barcode_mappings['case_controls']= barcode_mappings['cases'].map(decide_case_control)
        barcode_mappings_d2 = dict(barcode_mappings[['barcodes','case_controls']].values.tolist())
        self.pheno_sheet['Basename'] = self.pheno_sheet['bcr_patient_barcode'].map(barcode_mappings_d1)
        self.pheno_sheet['case_control'] = self.pheno_sheet['bcr_patient_barcode'].map(barcode_mappings_d2)
        idat_basenames = np.unique(np.vectorize(lambda x: '_'.join(x.split('/')[-1].split('_')[:2]))(idats))
        self.pheno_sheet = self.pheno_sheet[self.pheno_sheet['Basename'].isin(idat_basenames)]
        self.pheno_sheet.loc[:,['Basename']] = self.pheno_sheet['Basename'].map(lambda x: self.idat_dir+x)
        self.pheno_sheet = self.pheno_sheet[['Basename', 'bcr_patient_barcode', 'disease', 'tumor_stage', 'vital_status', 'age_at_diagnosis', 'gender', 'race', 'ethnicity','case_control']].rename(columns={'tumor_stage':'stage','bcr_patient_barcode':'PatientID','vital_status':'vital','gender':'Sex','age_at_diagnosis':'age'})

    def format_custom(self, basename_col, disease_class_column, include_columns={}):
        idats = glob.glob("{}/*.idat".format(self.idat_dir))
        idat_basenames = np.unique(np.vectorize(lambda x: '_'.join(x.split('/')[-1].split('_')[:-1]))(idats))
        idat_count_underscores = np.vectorize(lambda x: x.count('_'))(idat_basenames)
        self.pheno_sheet['Basename'] = self.pheno_sheet[basename_col]
        basename_count_underscores = np.vectorize(lambda x: x.count('_'))(self.pheno_sheet['Basename'])
        min_underscores=min(np.hstack([idat_count_underscores,basename_count_underscores]))
        basic_basename_fn = np.vectorize(lambda x: '_'.join(x.split('_')[-min_underscores-1:]))
        basic_basename=dict(zip(basic_basename_fn(self.pheno_sheet['Basename']),self.pheno_sheet['Basename'].values))
        basic_idat=dict(zip(basic_basename_fn(idat_basenames),idat_basenames))
        complete_mapping={basic_basename[basename]:basic_idat[basename] for basename in basic_basename}
        self.pheno_sheet.loc[:,'Basename']=self.pheno_sheet['Basename'].map(complete_mapping).map(lambda x: self.idat_dir+x)
        self.pheno_sheet['disease'] = self.pheno_sheet[disease_class_column.replace("'",'')]
        self.pheno_sheet = self.pheno_sheet[np.unique(['Basename', 'disease']+list(include_columns.keys()))].rename(columns=include_columns)

    def merge(self, other_formatted_sheet, use_second_sheet_disease=True):
        disease_dict = {False:'disease_x',True:'disease_y'}
        self.pheno_sheet = self.pheno_sheet.merge(other_formatted_sheet.pheno_sheet,how='inner', on='Basename')
        self.pheno_sheet['disease'] = self.pheno_sheet[disease_dict[use_second_sheet_disease]]
        cols=list(self.pheno_sheet)
        self.pheno_sheet = self.pheno_sheet[[col for col in cols if col!='Unnamed: 0_x' and col!='Unnamed: 0_y' and col!=disease_dict[use_second_sheet_disease]]]

    def concat(self, other_formatted_sheet):
        self.pheno_sheet=pd.concat([self.pheno_sheet,other_formatted_sheet.pheno_sheet],join='inner').reset_index(drop=True)
        self.pheno_sheet=self.pheno_sheet[[col for col in list(self.pheno_sheet) if not col.startswith('Unnamed:')]]

    def export(self, output_sheet_name):
        self.pheno_sheet.to_csv(output_sheet_name)
        print("Please move all other sample sheets out of this directory.")

    def split_key(self, key, subtype_delimiter):
        new_key = '{}_only'.format(key)
        self.pheno_sheet[new_key] = self.pheno_sheet[key].map(lambda x: x.split(subtype_delimiter)[0])
        return new_key

    def get_categorical_distribution(self, key, disease_only=False, subtype_delimiter=','):
        if type(key) == type('string'):
            if disease_only:
                key=self.split_key(key,subtype_delimiter)
            return Counter(self.pheno_sheet[key])
        else:
            cols=self.pheno_sheet[list(key)].astype(str)
            cols=reduce(lambda a,b: a+'_'+b,[cols.iloc[:,i] for i in range(cols.shape[1])])
            return Counter(cols)

    def remove_diseases(self,exclude_disease_list, low_count, disease_only,subtype_delimiter):
        if low_count:
            count_diseases=pd.DataFrame(self.get_categorical_distribution(low_count, disease_only,subtype_delimiter).items(),columns=['disease','count'])
            exclude_diseases_more=count_diseases.loc[count_diseases['count']<low_count,['disease']].unique().tolist()
            if disease_only:
                exclude_diseases_more=self.pheno_sheet.loc[self.pheno_sheet['disease_only'].isin(exclude_diseases_more),'disease'].unique().tolist()
        else:
            exclude_diseases_more=[]
        self.pheno_sheet = self.pheno_sheet[~self.pheno_sheet['disease'].isin(exclude_disease_list+exclude_diseases_more)]


class PreProcessIDAT:
    def __init__(self, idat_dir, minfi=None, enmix=None, base=None, meffil=None):
        self.idat_dir = idat_dir
        if minfi == None:
            self.minfi = importr('minfi')
        else:
            self.minfi = minfi
        if enmix == None:
            self.enmix = importr("ENmix")
        else:
            self.enmix = enmix
        if base == None:
            self.base = importr('base')
        else:
            self.base = base
        try:
            if meffil==None:
                self.meffil = importr('meffil')
            else:
                self.meffil = meffil
        except:
            self.meffil=None

    def preprocessRAW(self):
        self.MSet = self.minfi.preprocessRaw(self.RGset)
        return self.MSet

    def preprocessENmix(self, n_cores=6):
        self.qcinfo = self.enmix.QCinfo(self.RGset, detPthre=1e-7)
        self.MSet = self.enmix.preprocessENmix(self.RGset, QCinfo=self.qcinfo, nCores=n_cores)
        self.MSet = self.enmix.QCfilter(self.MSet,qcinfo=self.qcinfo,outlier=True)
        return self.MSet

    def preprocessMeffil(self, n_cores=6, n_pcs=4, qc_report_fname="qc/report.html", normalization_report_fname='norm/report.html'):
        self.pheno = self.meffil.meffil_read_samplesheet(self.idat_dir, verbose=True)
        self.beta_final = robjects.r("""function(samplesheet,n.cores,n.pcs,qc.report.fname,norm.report.fname){
            qc.objects<-meffil.qc(samplesheet,mc.cores=n.cores,verbose=F)
            qc.summary<-meffil.qc.summary(qc.objects,verbose=F)
            meffil.qc.report(qc.summary, output.file=qc.report.fname)
            if (nrow(qc.summary$bad.samples) > 0) {
            qc.objects <- meffil.remove.samples(qc.objects, qc.summary$bad.samples$sample.name)
            }
            norm.objects <- meffil.normalize.quantiles(qc.objects, number.pcs=n.pcs, verbose=F)
            norm <- meffil.normalize.samples(norm.objects, just.beta=F, cpglist.remove=qc.summary$bad.cpgs$name)
            pcs = meffil.methylation_pcs(norm)
            norm.summary = meffil.normalization.summary(norm.objects, pcs=pcs)
            meffil.normalization.report(norm.summary, output.file=norm.report.fname)
            beta <- meffil.get.beta(norm$M, norm$U)
            return(beta)}""")(self.pheno,n_cores, n_pcs, qc_report_fname, normalization_report_fname)

        try:
            grdevice = importr("grDevices")
            geneplotter = importr("geneplotter")
            qr_report_fname=os.path.abspath(qc_report_fname).split('/')
            qr_report_fname[-1]='beta_dist.jpg'
            grdevice.jpeg('/'.join(qr_report_fname),height=900,width=600)
            base.par(mfrow=robjects.vectors.IntVector([1,2]))
            self.enmix.multidensity(self.beta_final, main="Multidensity")
            self.enmix.multifreqpoly(self.beta_final, xlab="Beta value")
            grdevice.dev_off()
        except:
            pass

    def load_idats(self, geo_query=''):
        targets = self.minfi.read_metharray_sheet(self.idat_dir)
        self.RGset = self.minfi.read_metharray_exp(targets=targets, extended=True)
        if geo_query:
            geo = importr('GEOquery')
            self.RGset.slots["pData"] = robjects.r('pData')(robjects.r("getGEO('{}')[[1]]".format(query)))
        return self.RGset

    def plot_qc_metrics(self, output_dir):
        self.enmix.plotCtrl(self.RGset)
        grdevice = importr("grDevices")
        geneplotter = importr("geneplotter")
        base = importr('base')
        anno=self.minfi.getAnnotation(self.RGset)
        anno_py = pandas2ri.ri2py(robjects.r['as'](anno,'data.frame'))
        beta_py = pandas2ri.ri2py(self.beta)
        beta1=numpy2ri.py2ri(beta_py[anno_py["Type"]=="I"])
        beta2=numpy2ri.py2ri(beta_py[anno_py["Type"]=="II"])
        grdevice.jpeg(output_dir+'/dist.jpg',height=900,width=600)
        base.par(mfrow=robjects.vectors.IntVector([3,2]))
        self.enmix.multidensity(self.beta, main="Multidensity")
        self.enmix.multifreqpoly(self.beta, xlab="Beta value")
        self.enmix.multidensity(beta1, main="Multidensity: Infinium I")
        self.enmix.multifreqpoly(beta1, main="Multidensity: Infinium I", xlab="Beta value")
        self.enmix.multidensity(beta2, main="Multidensity: Infinium II")
        self.enmix.multifreqpoly(beta2, main="Multidensity: Infinium II", xlab="Beta value")
        grdevice.dev_off()
        self.minfi.qcReport(self.RGset, pdf = "{}/qcReport.pdf".format(output_dir))
        self.minfi.mdsPlot(self.RGset)
        self.minfi.densityPlot(self.RGset, main='Beta', xlab='Beta')

    def return_beta(self):
        self.RSet = self.minfi.ratioConvert(self.MSet, what = "both", keepCN = True)
        return self.RSet

    def get_beta(self):
        self.beta = self.minfi.getBeta(self.RSet)
        return self.beta

    def filter_beta(self):
        self.beta_final=self.enmix.rm_outlier(self.beta,qcscore=self.qcinfo)
        return self.beta_final

    def get_meth(self):
        return self.minfi.getMeth(self.MSet)

    def get_unmeth(self):
        return self.minfi.getUnmeth(self.MSet)

    def extract_pheno_data(self, methylset=False):
        self.pheno = robjects.r("pData")(self.MSet) if methylset else robjects.r("pData")(self.RGset)
        return self.pheno

    def extract_manifest(self):
        self.manifest = self.minfi.getManifest(self.RGset)
        return self.manifest

    def preprocess_enmix_pipeline(self, geo_query='', n_cores=6, pipeline='enmix'):
        self.load_idats(geo_query)
        if pipeline =='enmix':
            self.preprocessENmix(n_cores)
        else:
            self.preprocessRAW()
        self.return_beta()
        self.get_beta()
        self.filter_beta()
        self.extract_pheno_data(methylset=True)
        return self.pheno, self.beta_final

    def plot_original_qc(self, output_dir):
        self.preprocessRAW()
        self.return_beta()
        self.get_beta()
        self.plot_qc_metrics(output_dir)

    def output_pheno_beta(self, meffil=False):
        self.pheno_py=pandas2ri.ri2py(robjects.r['as'](self.pheno,'data.frame'))
        if not meffil:
            self.beta_py=pd.DataFrame(pandas2ri.ri2py(self.beta_final),index=numpy2ri.ri2py(robjects.r("featureNames")(self.RSet)),columns=numpy2ri.ri2py(robjects.r("sampleNames")(self.RSet))).transpose()
        else:
            self.beta_py=pd.DataFrame(pandas2ri.ri2py(self.beta_final),index=robjects.r("rownames")(self.beta_final),columns=robjects.r("colnames")(self.beta_final)).transpose()
            print(self.beta_py)
            print(self.beta_py.index)
            print(self.pheno_py)
            self.pheno_py = self.pheno_py.set_index('Sample_Name').loc[self.beta_py.index,:]

    def export_pickle(self, output_pickle, disease=''):
        output_dict = {}
        if os.path.exists(output_pickle):
            output_dict = pickle.load(open(output_pickle,'rb'))
        output_dict['pheno' if not disease else 'pheno_{}'.format(disease)] = self.pheno_py
        output_dict['beta' if not disease else 'beta_{}'.format(disease)] = self.beta_py
        pickle.dump(output_dict, open(output_pickle,'wb'),protocol=4)

    def export_sql(self, output_db, disease=''):
        conn = sqlite3.connect(output_db)
        self.pheno_py.to_sql('pheno' if not disease else 'pheno_{}'.format(disease), con=conn, if_exists='replace')
        self.beta_py.to_sql('beta' if not disease else 'beta_{}'.format(disease), con=conn, if_exists='replace')
        conn.close()

    def export_csv(self, output_dir):
        self.pheno_py.to_csv('{}/pheno.csv'.format(output_dir))
        self.beta_py.to_csv('{}/beta.csv'.format(output_dir))

    def to_methyl_array(self,disease=''):
        return MethylationArray(self.pheno_py,self.beta_py, disease)


class MethylationArray:
    def __init__(self, pheno_df, beta_df, name=''):
        self.pheno=pheno_df
        self.beta=beta_df
        self.name=name

    def export(self, output_pickle):
        pass

    def write_csvs(self, output_dir):
        self.pheno.to_csv('{}/pheno.csv'.format(output_dir))
        self.beta.to_csv('{}/beta.csv'.format(output_dir))

    def write_pickle(self, output_pickle, disease=''):
        output_dict = {}
        if 0 and os.path.exists(output_pickle):
            output_dict = pickle.load(open(output_pickle,'rb'))
        output_dict['pheno'] = self.pheno #  if not disease else 'pheno_{}'.format(disease)
        output_dict['beta'] = self.beta #  if not disease else 'beta_{}'.format(disease)
        pickle.dump(output_dict, open(output_pickle,'wb'),protocol=4)

    def write_db(self, conn, disease=''):
        self.pheno.to_sql('pheno' if not disease else 'pheno_{}'.format(disease), con=conn, if_exists='replace')
        self.beta.to_sql('beta' if not disease else 'beta_{}'.format(disease), con=conn, if_exists='replace')

    def impute(self, imputer):
        self.beta = pd.DataFrame(imputer.fit_transform(self.beta),index=self.beta.index,columns=list(self.beta))

    def return_shape(self):
        return self.beta.shape

    def split_train_test(self, train_p=0.8, stratified=True, disease_only=False, key='disease', subtype_delimiter=','):
        np.random.seed(42)
        if stratified:
            train_pheno=self.pheno.groupby(self.split_key('disease',subtype_delimiter) if disease_only else 'disease',group_keys=False).apply(lambda x: x.sample(frac=train_p))
        else:
            train_pheno = self.pheno.sample(frac=train_p)
        test_pheno = self.pheno.drop(train_pheno.index)
        return MethylationArray(train_pheno,self.beta.loc[train_pheno.index.values,:],'train'),MethylationArray(test_pheno,self.beta.loc[test_pheno.index.values,:],'test')

    def split_key(self, key, subtype_delimiter):
        new_key = '{}_only'.format(key)
        self.pheno[new_key] = self.pheno[key].map(lambda x: x.split(subtype_delimiter)[0])
        return new_key

    def split_by_subtype(self, disease_only, subtype_delimiter):
        for disease, pheno_df in self.pheno.groupby(self.split_key('disease',subtype_delimiter) if disease_only else 'disease'):
            new_disease_name = disease.replace(' ','')
            beta_df = self.beta.loc[pheno_df.index,:]
            yield MethylationArray(pheno_df,beta_df,new_disease_name)

    def feature_select(self, n_top_cpgs, feature_selection_method='mad', metric='correlation', nn=10):
        if feature_selection_method=='mad':
            mad_cpgs = self.beta.mad(axis=0).sort_values(ascending=False)
            top_mad_cpgs = np.array(list(mad_cpgs.iloc[:n_top_cpgs].index))
            self.beta = self.beta.loc[:, top_mad_cpgs]
        elif feature_selection_method=='spectral':
            from pynndescent.pynndescent_ import PyNNDescentTransformer
            from skfeature.function.similarity_based.SPEC import spec
            if nn:
                W=PyNNDescentTransformer(n_neighbors=nn,metric=metric).fit_transform(self.beta.values)
                print('W computed...')
                f_weights = spec(self.beta.values,W=W)
                print('weights',f_weights)
            else:
                f_weights = spec(self.beta.values)
            self.beta = self.beta.iloc[:, np.argsort(f_weights)[::-1][:n_top_cpgs]]


    def merge_preprocess_sheet(self, preprocess_sample_df):
        self.pheno=self.pheno.merge(preprocess_sample_df,on=['Basename'],how='inner')
        if 'disease_x' in list(self.pheno):
            self.pheno = self.pheno.rename(columns={'disease_x':'disease'})
        self.pheno = self.pheno[[col for col in list(self.pheno) if not col.startswith('Unnamed:')]]
        self.pheno=self.pheno.set_index([np.vectorize(lambda x: x.split('/')[-1])(self.pheno['Basename'])],drop=False)

    def load(self, input_pickle):
        pass

class MethylationArrays:
    def __init__(self, list_methylation_arrays):
        self.methylation_arrays = list_methylation_arrays

    def __len__(self):
        return len(self.methylation_arrays)

    def combine(self, array_generator=None): # FIXME add sort based on samples
        if len(self.methylation_arrays)> 1:
            pheno_df=pd.concat([methylArr.pheno for methylArr in self.methylation_arrays], join='inner')#.sort()
            beta_df=pd.concat([methylArr.beta for methylArr in self.methylation_arrays], join='inner')#.sort()
        else:
            pheno_df=self.methylation_arrays[0].pheno
            beta_df=self.methylation_arrays[0].beta
        if array_generator != None:
            for methylArr in array_generator:
                pheno_df=pd.concat([pheno_df,methylArr.pheno], join='inner')
                beta_df=pd.concat([beta_df,methylArr.beta], join='inner')
        return MethylationArray(pheno_df,beta_df)

    def write_dbs(self, conn):
        for methyl_arr in self.methylation_arrays:
            methyl_arr.write_db(conn, methyl_arr.name)

    def write_pkls(self,pkl):
        for methyl_arr in self.methylation_arrays:
            methyl_arr.write_pickle(pkl, methyl_arr.name)

    def impute(self, imputer):
        for i in range(len(self.methylation_arrays)):
            self.methylation_arrays[i].impute(imputer)

class ImputerObject:
    def __init__(self, solver, method, opts={}):
        from fancyimpute import KNN, NuclearNormMinimization, SoftImpute, IterativeImputer, BiScaler
        from sklearn.impute import SimpleImputer
        import inspect
        imputers = {'fancyimpute':dict(KNN=KNN,MICE=IterativeImputer,BiScaler=BiScaler,Soft=SoftImpute),
                    'impyute':dict(),
                    'simple':dict(Mean=SimpleImputer(strategy='mean'),Zero=SimpleImputer(strategy='constant'))}
        try:
            if solver == 'fancyimpute':
                f=imputers[solver][method]
                opts={key: opts[key] for key in opts if key in inspect.getargspec(f.__init__)[0]}
                self.imputer=f(**opts)
            else:
                self.imputer = imputers[solver][method]
        except:
            print('{} {} not a valid combination.\nValid combinations:{}'.format(
                solver, method, '\n'.join('{}:{}'.format(solver,','.join(imputers[solver].keys())) for solver in imputers)))
            exit()

    def return_imputer(self):
        return self.imputer

#### FUNCTIONS ####

def extract_pheno_beta_df_from_folder(folder):
    return pd.read_csv(folder+'/pheno.csv'), pd.read_csv(folder+'/beta.csv')

def extract_pheno_beta_df_from_pickle_dict(input_dict, disease=''):
    if disease:
        return input_dict['pheno_{}'.format(disease)], input_dict['beta_{}'.format(disease)]
    else:
        return input_dict['pheno'], input_dict['beta']

def extract_pheno_beta_df_from_sql(conn, disease=''):
    if disease:
        return pd.read_sql('select * from {};'.format('pheno_{}'.format(disease)),conn), pd.read_sql('select * from {};'.format('beta_{}'.format(disease)),conn)
    else:
        return pd.read_sql('select * from {};'.format('pheno'),conn), pd.read_sql('select * from {};'.format('beta'),conn)

#### COMMANDS ####

## Download ##

@preprocess.command()
@click.option('-o', '--output_dir', default='./tcga_idats/', help='Output directory for exported idats.', type=click.Path(exists=False), show_default=True)
def download_tcga(output_dir):
    """Download all tcga 450k data."""
    os.makedirs(output_dir, exist_ok=True)
    downloader = TCGADownloader()
    downloader.download_tcga(output_dir)

@preprocess.command()
@click.option('-o', '--output_dir', default='./tcga_idats/', help='Output directory for exported idats.', type=click.Path(exists=False), show_default=True)
def download_clinical(output_dir):
    """Download all 450k clinical info."""
    os.makedirs(output_dir, exist_ok=True)
    downloader = TCGADownloader()
    downloader.download_clinical(output_dir)

@preprocess.command()
@click.option('-g', '--geo_query', default='', help='GEO study to query.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./geo_idats/', help='Output directory for exported idats.', type=click.Path(exists=False), show_default=True)
def download_geo(geo_query,output_dir):
    """Download geo methylation study idats and clinical info."""
    os.makedirs(output_dir, exist_ok=True)
    downloader = TCGADownloader()
    downloader.download_geo(geo_query,output_dir)

## prepare

@preprocess.command()
@click.option('-is', '--input_sample_sheet', default='./tcga_idats/clinical_info.csv', help='Clinical information downloaded from tcga/geo/custom.', type=click.Path(exists=False), show_default=True)
@click.option('-s', '--source_type', default='tcga', help='Source type of data.', type=click.Choice(['tcga','geo','custom']), show_default=True)
@click.option('-i', '--idat_dir', default='./tcga_idats/', help='Idat directory.', type=click.Path(exists=False), show_default=True)
@click.option('-os', '--output_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='CSV for minfi input.', type=click.Path(exists=False), show_default=True)
@click.option('-m', '--mapping_file', default='./idat_filename_case.txt', help='Mapping file from uuid to TCGA barcode. Downloaded using download_tcga.', type=click.Path(exists=False), show_default=True)
@click.option('-l', '--header_line', default=0, help='Line to begin reading csv/xlsx.', show_default=True)
@click.option('-d', '--disease_class_column', default="methylation class:ch1", help='Disease classification column, for custom and geo datasets.', type=click.Path(exists=False), show_default=True)
@click.option('-b', '--basename_col', default="Sentrix ID (.idat)", help='Basename classification column, for custom datasets.', type=click.Path(exists=False), show_default=True)
@click.option('-c', '--include_columns_file', default="", help='Custom columns file containing columns to keep, separated by \\n. Add a tab for each line if you wish to rename columns: original_name \\t new_column_name', type=click.Path(exists=False), show_default=True)
def create_sample_sheet(input_sample_sheet, source_type, idat_dir, output_sample_sheet, mapping_file, header_line, disease_class_column, basename_col, include_columns_file):
    """Create sample sheet for input to minfi, meffil, or enmix."""
    os.makedirs(output_sample_sheet[:output_sample_sheet.rfind('/')], exist_ok=True)
    pheno_sheet = PreProcessPhenoData(input_sample_sheet, idat_dir, header_line= (0 if source_type != 'custom' else header_line))
    if include_columns_file:
        include_columns=np.loadtxt(include_columns_file,dtype=str,delimiter='\t')
        if '\t' in open(include_columns_file).read() and len(include_columns.shape)<2:
            include_columns=dict(include_columns[np.newaxis,:].tolist())
        elif len(include_columns.shape)<2:
            include_columns=dict(zip(include_columns,include_columns))
        else:
            include_columns=dict(include_columns.tolist())
    else:
        include_columns={}
    if source_type == 'tcga':
        pheno_sheet.format_tcga(mapping_file)
    elif source_type == 'geo':
        pheno_sheet.format_geo(disease_class_column, include_columns)
    else:
        pheno_sheet.format_custom(basename_col, disease_class_column, include_columns)
    pheno_sheet.export(output_sample_sheet)
    print("Please remove {} from {}, if it exists in that directory.".format(input_sample_sheet, idat_dir))

@preprocess.command()
@click.option('-is', '--input_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='CSV for minfi input.', type=click.Path(exists=False), show_default=True)
@click.option('-os', '--output_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='CSV for minfi input.', type=click.Path(exists=False), show_default=True)
def meffil_encode(input_sample_sheet,output_sample_sheet):
    """Reformat file for meffil input."""
    from collections import defaultdict
    pheno=pd.read_csv(input_sample_sheet)
    sex_dict=defaultdict(lambda:'NA')
    sex_dict.update({'m':'M','f':'F','M':'M','F':'F','male':'M','female':'F','nan':'NA',np.nan:'NA'})
    k='Sex' if 'Sex' in list(pheno) else 'sex'
    if k in list(pheno):
        pheno.loc[:,k] = pheno[k].map(lambda x: sex_dict[str(x).lower()])
    pheno = pheno[[col for col in list(pheno) if not col.startswith('Unnamed:')]].rename(columns={'sex':'Sex'})
    pheno.to_csv(output_sample_sheet)

@preprocess.command()
@click.option('-s1', '--sample_sheet1', default='./tcga_idats/clinical_info1.csv', help='Clinical information downloaded from tcga/geo/custom, formatted using create_sample_sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-s2', '--sample_sheet2', default='./tcga_idats/clinical_info2.csv', help='Clinical information downloaded from tcga/geo/custom, formatted using create_sample_sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-os', '--output_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='CSV for minfi input.', type=click.Path(exists=False), show_default=True)
@click.option('-d', '--second_sheet_disease', is_flag=True, help='Use second sheet\'s disease column.')
def merge_sample_sheets(sample_sheet1, sample_sheet2, output_sample_sheet, second_sheet_disease):
    """Merge two sample files for more fields for minfi+ input."""
    s1 = PreProcessPhenoData(sample_sheet1, idat_dir='', header_line=0)
    s2 = PreProcessPhenoData(sample_sheet2, idat_dir='', header_line=0)
    s1.merge(s2,second_sheet_disease)
    s1.export(output_sample_sheet)

@preprocess.command()
@click.option('-s1', '--sample_sheet1', default='./tcga_idats/clinical_info1.csv', help='Clinical information downloaded from tcga/geo/custom, formatted using create_sample_sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-s2', '--sample_sheet2', default='./tcga_idats/clinical_info2.csv', help='Clinical information downloaded from tcga/geo/custom, formatted using create_sample_sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-os', '--output_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='CSV for minfi input.', type=click.Path(exists=False), show_default=True)
def concat_sample_sheets(sample_sheet1, sample_sheet2, output_sample_sheet):
    """Concat two sample files for more fields for minfi+ input, adds more samples."""
    # FIXME add ability to concat more sample sheets; dump to sql!!!
    s1 = PreProcessPhenoData(sample_sheet1, idat_dir='', header_line=0)
    s2 = PreProcessPhenoData(sample_sheet2, idat_dir='', header_line=0)
    s1.concat(s2)
    s1.export(output_sample_sheet)

@preprocess.command()
@click.option('-is', '--formatted_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='Clinical information downloaded from tcga/geo/custom, formatted using create_sample_sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-k', '--key', multiple=True, default=['disease'], help='Column of csv to print statistics for.', type=click.Path(exists=False), show_default=True)
@click.option('-d', '--disease_only', is_flag=True, help='Only look at disease, or text before subtype_delimiter.')
@click.option('-sd', '--subtype_delimiter', default=',', help='Delimiter for disease extraction.', type=click.Path(exists=False), show_default=True)
def get_categorical_distribution(formatted_sample_sheet,key,disease_only=False,subtype_delimiter=','):
    """Get categorical distribution of columns of sample sheet."""
    if len(key) == 1:
        key=key[0]
    print('\n'.join('{}:{}'.format(k,v) for k,v in PreProcessPhenoData(formatted_sample_sheet, idat_dir='', header_line=0).get_categorical_distribution(key,disease_only,subtype_delimiter).items()))

@preprocess.command()
@click.option('-is', '--formatted_sample_sheet', default='./tcga_idats/clinical_info.csv', help='Clinical information downloaded from tcga/geo/custom, formatted using create_sample_sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-e', '--exclude_disease_list', default='', help='List of conditions to exclude, from disease column.', type=click.Path(exists=False), show_default=True)
@click.option('-os', '--output_sample_sheet', default='./tcga_idats/minfiSheet.csv', help='CSV for minfi input.', type=click.Path(exists=False), show_default=True)
@click.option('-l', '--low_count', default=0, help='Remove diseases if they are below a certain count, default this is not used.', type=click.Path(exists=False), show_default=True)
@click.option('-d', '--disease_only', is_flag=True, help='Only look at disease, or text before subtype_delimiter.')
@click.option('-sd', '--subtype_delimiter', default=',', help='Delimiter for disease extraction.', type=click.Path(exists=False), show_default=True)
def remove_diseases(formatted_sample_sheet, exclude_disease_list, output_sheet_name, low_count, disease_only=False,subtype_delimiter=','):
    """Exclude diseases from study by count number or exclusion list."""
    exclude_disease_list = exclude_disease_list.split(',')
    pData = PreProcessPhenoData(formatted_sample_sheet, idat_dir='', header_line=0)
    pData.remove_diseases(exclude_disease_list,low_count, disease_only,subtype_delimiter)
    pData.export(output_sheet_name)
    print("Please remove {} from idat directory, if it exists in that directory.".format(formatted_sample_sheet))

## preprocess ##

@preprocess.command()
@click.option('-i', '--idat_csv', default='./tcga_idats/minfiSheet.csv', help='Idat csv for one sample sheet, alternatively can be your phenotype sample sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-g', '--geo_query', default='', help='GEO study to query, do not use if already created geo sample sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-d', '--disease_only', is_flag=True, help='Only look at disease, or text before subtype_delimiter.')
@click.option('-sd', '--subtype_delimiter', default=',', help='Delimiter for disease extraction.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--subtype_output_dir', default='./preprocess_outputs/', help='Output subtypes pheno csv.', type=click.Path(exists=False), show_default=True)
def split_preprocess_input_by_subtype(idat_csv,geo_query,disease_only,subtype_delimiter, subtype_output_dir):
    """Split preprocess input samplesheet by disease subtype."""
    from collections import defaultdict
    subtype_delimiter=subtype_delimiter.replace('"','').replace("'","")
    os.makedirs(subtype_output_dir,exist_ok=True)
    pData=PreProcessPhenoData(idat_csv,'')
    idat_csv_basename = idat_csv.split('/')[-1]
    group_by_key = (pData.split_key('disease',subtype_delimiter) if disease_only else 'disease')
    pData_grouped = pData.pheno_sheet.groupby(group_by_key)
    for name, group in pData_grouped:
        name=name.replace(' ','')
        new_sheet = idat_csv_basename.replace('.csv','_{}.csv'.format(name))
        new_out_dir = '{}/{}/'.format(subtype_output_dir,name)
        os.makedirs(new_out_dir, exist_ok=True)
        print(new_out_dir)
        if 'Sex' in list(group):
            d=defaultdict(lambda:'NA')
            d.update({'M':'M','F':'F'})
            group.loc[:,'Sex'] = group['Sex'].map(d)
            if (group['Sex']==group['Sex'].mode().values[0][0]).all():
                group=group.rename(columns={'Sex':'gender'})
        group.to_csv('{}/{}'.format(new_out_dir,new_sheet))

@preprocess.command()
@click.option('-n', '--n_cores', default=6, help='Number cores to use for preprocessing.', show_default=True)
@click.option('-i', '--subtype_output_dir', default='./preprocess_outputs/', help='Output subtypes pheno csv.', type=click.Path(exists=False), show_default=True)
@click.option('-m', '--meffil', is_flag=True, help='Preprocess using meffil.')
@click.option('-t', '--torque', is_flag=True, help='Job submission torque.')
@click.option('-r', '--run', is_flag=True, help='Actually run local job or just print out command.')
@click.option('-s', '--series', is_flag=True, help='Run commands in series.')
def batch_deploy_preprocess(n_cores,subtype_output_dir,meffil,torque,run,series):
    """Deploy multiple preprocessing jobs in series or parallel."""
    pheno_csvs = glob.glob(os.path.join(subtype_output_dir,'*','*.csv'))
    opts = {'-n':n_cores}
    if meffil:
        opts['-m']=''
    commands=[]
    for pheno_csv in pheno_csvs:
        pheno_path = os.path.abspath(pheno_csv)
        opts['-i']=pheno_path[:pheno_path.rfind('/')+1]
        opts['-o']=pheno_path[:pheno_path.rfind('/')+1]+'methyl_array.pkl'
        command='python preprocess.py preprocess_pipeline {}'.format(' '.join('{} {}'.format(k,v) for k,v in opts.items()))
        commands.append(command)
    if not torque:
        for command in commands:
            if not series:
                command="nohup {} &".format(command)
            if not run:
                click.echo(command)
            else:
                subprocess.call(command,shell=True)
    else:
        run_command = lambda command: subprocess.call('module load cuda && module load python/3-Anaconda && source activate py36 && {}'.format(command),shell=True)
        from pyina.schedulers import Torque
        from pyina.launchers import Mpi
        config = {'nodes':'10:ppn=6', 'queue':'default', 'timelimit':'01:00'}
        torque = Torque(**config)
        pool = Mpi(scheduler=torque)
        pool.map(run_command, commands)

@preprocess.command()
@click.option('-i', '--idat_dir', default='./tcga_idats/', help='Idat dir for one sample sheet, alternatively can be your phenotype sample sheet.', type=click.Path(exists=False), show_default=True)
@click.option('-n', '--n_cores', default=6, help='Number cores to use for preprocessing.', show_default=True)
@click.option('-o', '--output_pkl', default='./preprocess_outputs/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-m', '--meffil', is_flag=True, help='Preprocess using meffil.')
@click.option('-p', '--pipeline', default='enmix', show_default=True, help='If not meffil, preprocess using minfi or enmix.', type=click.Choice(['minfi','enmix']))
def preprocess_pipeline(idat_dir, n_cores, output_pkl, meffil, pipeline):
    """Perform preprocessing of idats using enmix or meffil."""
    output_dir = output_pkl[:output_pkl.rfind('/')]
    os.makedirs(output_dir,exist_ok=True)
    preprocesser = PreProcessIDAT(idat_dir)
    if meffil:
        preprocesser.preprocessMeffil(n_cores=n_cores,n_pcs=4,qc_report_fname=os.path.join(output_dir,'qc.report.html'), normalization_report_fname=os.path.join(output_dir,'norm.report.html'))
    else:
        preprocesser.preprocess_enmix_pipeline(geo_query='', n_cores=n_cores, pipeline=pipeline)
        try:
            preprocesser.plot_qc_metrics(output_dir)
        except:
            pass
    preprocesser.output_pheno_beta(meffil=meffil)
    preprocesser.to_methyl_array('').write_pickle(output_pkl)

@preprocess.command()
@click.option('-i', '--input_pkls', default=['./preprocess_outputs/methyl_array.pkl'], multiple=True, help='Input pickles for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-d', '--optional_input_pkl_dir', default='', help='Auto grab input pkls.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./combined_outputs/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-e', '--exclude', default=[], multiple=True, help='If -d selected, these diseases will be excluded from study.', show_default=True)
def combine_methylation_arrays(input_pkls, optional_input_pkl_dir, output_pkl, exclude):
    """If split MethylationArrays by subtype for either preprocessing or imputation, can use to recombine data for downstream step."""
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    if optional_input_pkl_dir:
        input_pkls=glob.glob(os.path.join(optional_input_pkl_dir,'*','methyl_array.pkl'))
        if exclude:
            input_pkls=(np.array(input_pkls)[~np.isin(np.vectorize(lambda x: x.split('/')[-2])(input_pkls),np.array(exclude))]).tolist()
    if len(input_pkls) > 0:
        base_methyl_array=MethylationArray(*extract_pheno_beta_df_from_pickle_dict(pickle.load(open(input_pkls[0],'rb')), ''))
        methyl_arrays_generator = (MethylationArray(*extract_pheno_beta_df_from_pickle_dict(pickle.load(open(input_pkl,'rb')), '')) for input_pkl in input_pkls[1:])
        list_methyl_arrays = MethylationArrays([base_methyl_array])
        combined_methyl_array = list_methyl_arrays.combine(methyl_arrays_generator)
    else:
        combined_methyl_array=MethylationArray(*extract_pheno_beta_df_from_pickle_dict(pickle.load(open(input_pkls[0],'rb')), ''))
    combined_methyl_array.write_pickle(output_pkl)

@preprocess.command()
@click.option('-i', '--input_pkl', default='./combined_outputs/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-ss', '--split_by_subtype', is_flag=True, help='Imputes CpGs by subtype before combining again.')
@click.option('-m', '--method', default='KNN', help='Method of imputation.', type=click.Choice(['KNN', 'Mean', 'Zero', 'MICE', 'BiScaler', 'Soft', 'random', 'DeepCpG', 'DAPL']), show_default=True)
@click.option('-s', '--solver', default='fancyimpute', help='Imputation library.', type=click.Choice(['fancyimpute', 'impyute', 'simple']), show_default=True)
@click.option('-k', '--n_neighbors', default=5, help='Number neighbors for imputation if using KNN.', show_default=True)
@click.option('-r', '--orientation', default='Samples', help='Impute CpGs or samples.', type=click.Choice(['Samples','CpGs']), show_default=True)
@click.option('-o', '--output_pkl', default='./imputed_outputs/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-n', '--n_top_cpgs', default=0, help='Number cpgs to include with highest variance across population. Greater than 0 allows for mad filtering during imputation to skip mad step.', show_default=True)
@click.option('-f', '--feature_selection_method', default='mad', type=click.Choice(['mad','spectral']))
@click.option('-mm', '--metric', default='correlation', type=click.Choice(['euclidean','cosine','correlation']))
@click.option('-nfs', '--n_neighbors_fs', default=0, help='Number neighbors for feature selection, default enacts rbf kernel.', show_default=True)
@click.option('-d', '--disease_only', is_flag=True, help='Only look at disease, or text before subtype_delimiter.')
@click.option('-sd', '--subtype_delimiter', default=',', help='Delimiter for disease extraction.', type=click.Path(exists=False), show_default=True)
def imputation_pipeline(input_pkl,split_by_subtype=True,method='knn', solver='fancyimpute', n_neighbors=5, orientation='rows', output_pkl='', n_top_cpgs=0, feature_selection_method='mad', metric='correlation', n_neighbors_fs=10, disease_only=False, subtype_delimiter=','): # wrap a class around this
    """Imputation of subtype or no subtype using various imputation methods."""
    orientation_dict = {'CpGs':'columns','Samples':'rows'}
    orientation = orientation_dict[orientation]
    #print("Selecting orientation for imputation not implemented yet.")
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    if method in ['DeepCpG', 'DAPL', 'EM']:
        print('Method {} coming soon...'.format(method))
    elif solver in ['impyute']:
        print('Impyute coming soon...')
    else:
        imputer = ImputerObject(solver, method, opts=dict(k=n_neighbors, orientation=orientation)).return_imputer()
    input_dict = pickle.load(open(input_pkl,'rb'))

    if split_by_subtype:

        def impute_arrays(methyl_arrays):
            for methyl_array in methyl_arrays:
                methyl_array.impute(imputer)
                yield methyl_array

        methyl_array = MethylationArray(*extract_pheno_beta_df_from_pickle_dict(input_dict))
        methyl_arrays = impute_arrays(methyl_array.split_by_subtype(disease_only, subtype_delimiter))
        methyl_array=MethylationArrays([next(methyl_arrays)]).combine(methyl_arrays)

    else:
        methyl_array = MethylationArray(*extract_pheno_beta_df_from_pickle_dict(input_dict))

        methyl_array.impute(imputer)

    if n_top_cpgs:
        methyl_array.feature_select(n_top_cpgs,feature_selection_method, metric, nn=n_neighbors_fs)

    methyl_array.write_pickle(output_pkl)

@preprocess.command()
@click.option('-i', '--input_pkl', default='./imputed_outputs/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./final_preprocessed/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-n', '--n_top_cpgs', default=300000, help='Number cpgs to include with highest variance across population.', show_default=True)
@click.option('-f', '--feature_selection_method', default='mad', type=click.Choice(['mad','spectral']))
@click.option('-m', '--metric', default='correlation', type=click.Choice(['euclidean','cosine','correlation']))
@click.option('-nn', '--n_neighbors', default=0, help='Number neighbors for feature selection, default enacts rbf kernel.', show_default=True)
@click.option('-m', '--mad_top_cpgs', default=0, help='Number cpgs to apply mad filtering first before more sophisticated feature selection. If 0, no mad pre-filtering.', show_default=True)
def feature_select(input_pkl,output_pkl,n_top_cpgs=300000, feature_selection_method='mad', metric='correlation', n_neighbors=10, mad_top_cpgs=0):
    """Filter CpGs by taking x top CpGs with highest mean absolute deviation scores or via spectral feature selection."""
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    input_dict=pickle.load(open(input_pkl,'rb'))
    methyl_array = MethylationArray(*extract_pheno_beta_df_from_pickle_dict(input_dict))

    if mad_top_cpgs:
        methyl_array.feature_select(mad_top_cpgs,'mad')

    methyl_array.feature_select(n_top_cpgs,feature_selection_method, metric, nn=n_neighbors)

    methyl_array.write_pickle(output_pkl)

### QC

@preprocess.command()
@click.option('-i', '--input_pkl', default='./preprocess_outputs/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./na_report/', help='Output database for na report.', type=click.Path(exists=False), show_default=True)
def na_report(input_pkl, output_dir):
    """Print proportion of missing values throughout dataset."""
    import matplotlib.pyplot as plt
    os.makedirs(output_dir,exist_ok=True)
    df=pickle.load(open(input_pkl,'rb'))['beta']
    na_frame = pd.isna(df.values).astype(int)
    na_frame = na_frame.iloc[np.argsort(na_frame.sum(axis=1)),:]
    print('NA Rate is on average: {}%'.format(sum(na_frame.values.flatten())/float(df.shape[0]*df.shape[1])*100.))
    plt.figure()
    pd.DataFrame(na_frame.sum(axis=1)).apply(lambda x: x/float(df.shape[1])).hist()
    plt.savefig(os.path.join(output_dir,'sample_missingness.png'))
    plt.figure()
    pd.DataFrame(na_frame.sum(axis=0)).apply(lambda x: x/float(df.shape[0])).hist()
    plt.savefig(os.path.join(output_dir,'cpg_missingness.png'))
    xy=np.transpose(np.nonzero(na_frame.values))
    plt.figure()
    plt.scatter(xy[:,1],xy[:,0])
    plt.xlim([0,df.shape[0]])
    plt.ylim([0,df.shape[1]])
    plt.xlabel('CpGs')
    plt.ylabel('Samples')
    plt.savefig(os.path.join(output_dir,'array_missingness.png'))



### MISC

@preprocess.command()
@click.option('-i', '--input_dir', default='./', help='Directory containing jpg.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./preprocess_output_images/', help='Output directory for images.', type=click.Path(exists=False), show_default=True)
def move_jpg(input_dir, output_dir):
    """Move preprocessing jpegs to preprocessing output directory."""
    os.makedirs(output_dir, exist_ok=True)
    subprocess.call('mv {} {}'.format(os.path.join(input_dir,'*.jpg'),os.path.abspath(output_dir)),shell=True)

@preprocess.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_pkl', default='./backup/methyl_array.pkl', help='Output database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def backup_pkl(input_pkl, output_pkl):
    """Copy methylarray pickle to new location to backup."""
    os.makedirs(output_pkl[:output_pkl.rfind('/')],exist_ok=True)
    subprocess.call('rsync {} {}'.format(input_pkl, output_pkl),shell=True)

@preprocess.command()
@click.option('-i', '--input_pkl', default='./final_preprocessed/methyl_array.pkl', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
@click.option('-o', '--output_dir', default='./final_preprocessed/', help='Input database for beta and phenotype data.', type=click.Path(exists=False), show_default=True)
def pkl_to_csv(input_pkl, output_dir):
    """Output methylarray pickle to csv."""
    os.makedirs(output_dir,exist_ok=True)
    input_dict=pickle.load(open(input_pkl,'rb'))
    for k in input_dict.keys():
        input_dict[k].to_csv('{}/{}.csv'.format(output_dir,k))

@preprocess.command()
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


#################

if __name__ == '__main__':
    preprocess()