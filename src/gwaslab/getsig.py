import pandas as pd
import numpy as np
import scipy as sp
from gwaslab.Log import Log
from gwaslab.CommonData import get_chr_to_number
from gwaslab.CommonData import get_number_to_chr
from pyensembl import EnsemblRelease
from pyensembl import Genome

def getsig(insumstats,
           id,
           chrom,
           pos,
           p,
           windowsizekb=500,
           sig_level=5e-8,
           log=Log(),
           xymt=["X","Y","MT"],
           anno=False,
           build="19",
           verbose=True):
    
    if verbose: log.write("Start to extract lead variants...")
    if verbose: log.write(" -Processing "+str(len(insumstats))+" variants...")
    if verbose: log.write(" -Significance threshold :", sig_level)
    if verbose: log.write(" -Sliding window size:", str(windowsizekb) ," kb")
    #load data
    
    sumstats=insumstats.loc[~insumstats[id].isna(),:].copy()
    
    #convert chrom to int
    if sumstats[chrom].dtype in ["object",str,pd.StringDtype]:
        chr_to_num = get_chr_to_number(out_chr=True,xymt=["X","Y","MT"])
        sumstats[chrom]=sumstats[chrom].map(chr_to_num)
    
    sumstats[chrom] = np.floor(pd.to_numeric(sumstats[chrom], errors='coerce')).astype('Int64')
    sumstats[pos] = np.floor(pd.to_numeric(sumstats[pos], errors='coerce')).astype('Int64')
    sumstats[p] = pd.to_numeric(sumstats[p], errors='coerce')
    
    #extract all significant variants
    sumstats_sig = sumstats.loc[sumstats[p]<sig_level,:]
    if verbose:log.write(" -Found "+str(len(sumstats_sig))+" significant variants in total...")
    
    #sort the coordinates
    sumstats_sig = sumstats_sig.sort_values([chrom,pos])
    
    if sumstats_sig is None:
        if verbose:log.write(" -No lead snps at given significance threshold!")
        return None
    
    sig_index_list=[]
    current_sig_index = False
    current_sig_p = 1
    current_sig_pos = 0
    current_sig_chr = 0
    
    #iterate through all significant snps
    for line_number,(index, row) in enumerate(sumstats_sig.iterrows()):
        #when finished one chr 
        if row[chrom]!=current_sig_chr:
            #add the current lead variants id to lead variant list
            if current_sig_index is not False:sig_index_list.append(current_sig_index)
            
            #update lead vairant info to the new variant
            current_sig_chr=row[chrom]
            current_sig_pos=row[pos]
            current_sig_p=row[p]
            current_sig_index=row[id]
            
            # only one significant variant on a new chromsome and this is the last sig variant
            if  line_number == len(sumstats_sig)-1:
                sig_index_list.append(current_sig_index)
            continue
        
        # next loci : gap > windowsizekb*1000
        if row[pos]>current_sig_pos + windowsizekb*1000:
            sig_index_list.append(current_sig_index)
            current_sig_pos=row[pos]
            current_sig_p=row[p]
            current_sig_index=row[id]
            continue
        
        # update current pos and p
        if row[p]<current_sig_p:
            current_sig_pos=row[pos]
            current_sig_p=row[p]
            current_sig_index=row[id]
        else:
            current_sig_pos=row[pos]
            
        #when last line in sig_index_list
        if  line_number == len(sumstats_sig)-1:
            sig_index_list.append(current_sig_index)
            continue
    
    if verbose:log.write(" -Identified "+str(len(sig_index_list))+" lead variants!")
    
    #num_to_chr = get_number_to_chr(in_chr=True,xymt=xymt)
    #sumstats_sig.loc[:,chrom] = sumstats_sig[chrom].astype("string")
    #sumstats_sig.loc[:,chrom] = sumstats_sig.loc[:,chrom].map(num_to_chr)
    output = sumstats_sig.loc[sumstats_sig[id].isin(sig_index_list),:].copy()
    if anno is True:
        if build=="19":
            data = EnsemblRelease(75)
            if verbose:log.write(" -Assigning Gene name using Ensembl Release",75 , " (hg19)")
        elif build=="38":
            data = EnsemblRelease(77)
            if verbose:log.write(" -Assigning Gene name using Ensembl Release",77 , " (hg38)")
        output.loc[:,["LOCATION","GENE"]] = pd.DataFrame(output.apply(lambda x:closest_gene(x,data=data), axis=1).tolist(), index=output.index).values
    if verbose: log.write("Finished extracting lead variants successfully!")
    return output.copy()


def closest_gene(x,data,chrom="CHR",pos="POS",maxiter=20000,step=50):
        #
        # data
        # check snp position
        #convert 23,24,25 back to X,Y,MT for EnsemblRelease query
        x[chrom] = get_number_to_chr()[x[chrom]]
         
        # query
        gene = data.gene_names_at_locus(contig= x[chrom], position=x[pos])
        if len(gene)==0:
            # if not in any gene
            i=0
            while i<=maxiter:
                # using distance to check upstram and downstream region
                distance = i*step
                # upstream
                gene_u = data.gene_names_at_locus(contig=x[chrom], position=x[pos]-distance)
                
                # downstream
                gene_d = data.gene_names_at_locus(contig=x[chrom], position=x[pos]+distance)
                
                if len(gene_u)>0 and len(gene_d)>0:
                    # if found gene uptream and downstream at the same time 
                    # go back to last step
                    distance = (i-1)*step
                    for j in range(0,step,1):
                        # use small step to finemap                        
                        gene_u = data.gene_names_at_locus(contig=x[chrom], position=x[pos]-distance-j)
                        gene_d = data.gene_names_at_locus(contig=x[chrom], position=x[pos]+distance+j)
                        if len(gene_u)>0:
                            return -distance-j,",".join(gene_u)
                        elif len(gene_d)>0:
                            return distance+j,",".join(gene_d)
                elif len(gene_u)>0:                    
                    # if found gene uptream
                    for j in range(0,step,1):
                        gene_u2 = data.gene_names_at_locus(contig=x[chrom], position=x[pos]-distance+j)
                        if len(gene_u2)==0:
                            return -distance+j,",".join(gene_u)
                elif len(gene_d)>0:
                    # if found gene downstream
                    for j in range(0,step,1):
                        gene_d2 = data.gene_names_at_locus(contig=x[chrom], position=x[pos]+distance-j)
                        if len(gene_d2)==0:
                            return distance-j,",".join(gene_d)
                i+=1
                # increase i by 1
            return distance,"intergenic"
        else:
            return 0,",".join(gene)
        
        
def annogene(
           insumstats,
           id,
           chrom,
           pos,
           log=Log(),
           xymt=["X","Y","MT"],
           build="19",
           verbose=True):
    output = insumstats.copy()
    
    if build=="19":
        #data = EnsemblRelease(75)
        if verbose:log.write(" -Assigning Gene name using Ensembl Release",75 , " (hg19)")
        data = Genome(
        reference_name='GRCh37',
        annotation_name='genes',
        gtf_path_or_url='/home/yunye/mydata/d_disk/gene/Homo_sapiens.GRCh37.75.protein_coding.chr.gtf.gz')
        output.loc[:,["LOCATION","GENE"]] = pd.DataFrame(output.apply(lambda x:closest_gene(x,data=data), axis=1).tolist(), index=output.index).values
    elif build=="38":
        data = EnsemblRelease(77)
        if verbose:log.write(" -Assigning Gene name using Ensembl Release",77 , " (hg38)")
        output.loc[:,["LOCATION","GENE"]] = pd.DataFrame(output.apply(lambda x:closest_gene(x,data=data), axis=1).tolist(), index=output.index).values
    if verbose: log.write("Finished extracting lead variants successfully!")
    return output