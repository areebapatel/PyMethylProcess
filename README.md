## PyMethylProcess

![pymethylprocess_overview](https://user-images.githubusercontent.com/19698023/54838986-4e152e00-4ca0-11e9-9012-a6d710fffee3.jpeg)

https://github.com/Christensen-Lab-Dartmouth/PyMethylProcess  

Help documentation: https://christensen-lab-dartmouth.github.io/PyMethylProcess/  

Alternatively, you can access the pdf: PyMethylProcess.pdf

What is it:
* Preprocess 450k and 850k methylation IDAT files in parallel using Minfi, ENmix, and meffil  
* Convenient and scalable implementation  
* Imputation and Feature Selection  
* Preparation for machine learning pipelines    

Why:
* Make DNAm accessible to python developers and more machine learning oriented researchers  
* Streamlined analysis makes processing easy  

*PyMethyProcess* is pending submission and review, biorxiv: https://www.biorxiv.org/content/biorxiv/early/2019/04/13/604496.full.pdf.  

Getting Started:  
* Installation:   
    * pip install git+https://github.com/bodono/scs-python.git@bb45c69ce57b1fbb5ab23e02b30549a7e0b801e3 git+https://github.com/jlevy44/hypopt.git@af59fbed732f5377cda73fdf42f3d4981c2be3ce
    * pip install pymethylprocess && pymethyl-install_r_dependencies (Note: May need to prefix pip install with MACOSX_DEPLOYMENT_TARGET=10.9 CC=clang CXX=clang++ for Mac OS install)
    * docker pull joshualevy44/pymethylprocess:0.1.3
    * Alternatively, run sh build_docker.sh to build the docker container, and then run sh run_docker.sh to run the docker container.
    * Or see example scripts for usage.
* Example Usage Scripts (in github repo): Located in ./example_scripts/  
* Help docs (in github repo): https://christensen-lab-dartmouth.github.io/PyMethylProcess/

**Benchmark Results:**
<img width="1297" alt="benchmark" src="https://user-images.githubusercontent.com/19698023/55841697-422dc680-5afe-11e9-815d-dda140626c7c.png">

**Supplementary Figure Removed from Manuscript:**
![Supplemental](https://user-images.githubusercontent.com/19698023/55841691-380bc800-5afe-11e9-9411-d428efa1070e.jpeg)

**Supplemental Figure 1:** UMAP embeddings (colored) of: a) GSE87571 (age), b) GSE81961 (disease status), c) GSE69138 (subtype), d) GSE42861 (disease status), e) GSE112179 (brain disorder), f) GSE90496 (subclass), g) TCGA Pancancer (subtype)  

![pipeline-download](https://user-images.githubusercontent.com/19698023/54839004-566d6900-4ca0-11e9-97fa-f338d11b896b.jpeg)  
![pipeline-format](https://user-images.githubusercontent.com/19698023/54839010-59685980-4ca0-11e9-92da-58bccec68347.jpeg)  
![pipeline-preprocess](https://user-images.githubusercontent.com/19698023/54839016-5cfbe080-4ca0-11e9-8c7e-22a871483d16.jpeg)  
![pipeline-visualize](https://user-images.githubusercontent.com/19698023/56082165-48f05e00-5dca-11e9-863b-682a5d4c325f.jpeg)
![pipeline-train-test-split](https://user-images.githubusercontent.com/19698023/54839060-713fdd80-4ca0-11e9-85a8-9385012a6807.jpeg)  
