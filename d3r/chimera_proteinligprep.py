#!/usr/bin/evn python

import commands
import os
import glob
import logging
import time

logger = logging.getLogger()
logging.basicConfig( format  = '%(asctime)s: %(message)s', datefmt = '%m/%d/%y %I:%M:%S', filename = 'final.log', filemode = 'w', level   = logging.DEBUG )

#challenge_data_path = "/data/celpp/2015/dataset.week.47/stage.2.blastnfilter"
#pdb_protein_location = "/data/pdb.extracted"
#full_copy_location = ""
#target_copy_location = ""

chimera_prep_text = '''
import chimera
import sys
opened = chimera.openModels.open(sys.argv[1])
mol = opened[0]

import DockPrep

DockPrep.prep([mol])
from WriteMol2 import writeMol2
with open(sys.argv[2],'wb') as of:
    writeMol2([mol], of)
'''


def extract_info_from_s2(stage_2_out):
    info_dic = {}
    f = open(stage_2_out,"r")
    lines = f.readlines()
    f.close()
    for line in lines:
        #print line.split(",")[0]
        info_title = line.split(",")[0]
        info_value_1 = line.split(",")[1] 
        if line.split(",")[0] == "inchi":
            info_title = line.split(", InChI=")[0] 
            info_value_1 = line.split(", InChI=")[1].split("\n")[0]
        else:
            try:
                info_value_2 = line.split(",")[2].split("\n")[0].strip()
                info_title = line.split(",")[0]
                info_value_1 = line.split(",")[1].strip() 
            except:
                info_value_2 = False
                info_title = line.split(",")[0]
                info_value_1 = line.split(",")[1].split("\n")[0].strip()
                pass
        #if not 
        if not info_value_2:
            #just use the first item if there are multiple entries (use the highest resolution one)
            if info_title not in info_dic:
                info_dic[info_title] = info_value_1
        else:
            if info_title not in info_dic:
                info_dic[info_title] = (info_value_1,info_value_2) 
    return info_dic

#copy all the txt files from the output stage 2 location and create folder for each of this named by the query entry
#check if it finished later needed 
def get_center(protein_file, ligname):
    xyz_lines = open(protein_file,"r").readlines()
    multi_ligand = False
    atom_list = []
    x = y = z = 0
    for xyz_line in xyz_lines:
        if "HETATM" in xyz_line and ligname in xyz_line[17:21]:
            #logging.debug("Check the get center of this protein: %s for this ligand: %s"%(protein_file, ligname))
            atom_name = xyz_line[12:16]
            if atom_name in atom_list:
                multi_ligand = True
            else:
                atom_list.append(atom_name)
                try:
                    x += float(xyz_line[30:38])
                    y+= float(xyz_line[38:46])
                    z+= float(xyz_line[46:54])
                except:
                    logging.debug("Fatal error: Cannot find the XYZ coordinate for this protein:%s"%protein_file)
                    return False
    if not multi_ligand:
        lig_center = "%8.3f, %8.3f, %8.3f"%(x/len(atom_list), y/len(atom_list), z/len(atom_list))
        logging.debug("Ligand center for this case:%s is %s"%(protein_file, lig_center))
        return lig_center
    else:
        logging.debug("Fatal error: Found multiple ligand for this protein:%s"%protein_file)
        return False

def ligand_prepare(ligand_smile, out_lig_file):
#    commands.getoutput("$SCHRODINGER/ligprep -WAIT -i 0 -nt -s 1 -g -ismi %s -omae %s"%(ligand_smile, out_lig_file) ) 
#    return os.path.isfile(out_lig_file)
    if os.path.isfile(out_lig_file):
        logging.info('Ligand file %s is already prepared. Skipping.' %(out_lig_file))
        return True
    # Prepare a 3D version of the ligand using babel
    unprep_lig_file = ligand_smile.replace('.smi','_unprep.mol2')
    commands.getoutput('babel -ismi %s -omol2 %s --gen3D' %(ligand_smile,unprep_lig_file))
    with open('chimeraPrep.py','wb') as of:
        of.write(chimera_prep_text) 
    commands.getoutput('chimera --nogui --script "chimeraPrep.py %s %s" >& chimeraLigPrep.out' %(unprep_lig_file, out_lig_file))
    #time.sleep(sleep_time) 
    return os.path.isfile(out_lig_file)


def align_proteins (target_protein, pre_prepare_protein, post_prepare_protein):
    commands.getoutput("$SCHRODINGER/utilities/structalign %s %s"%(target_protein, pre_prepare_protein))
    rotated_protein = "rot-" + pre_prepare_protein
    if os.path.isfile(rotated_protein):
        commands.getoutput("mv %s %s"%(rotated_protein, post_prepare_protein))
        return True
    else:
        return False

def split_complex (part, complex_file, out_split):
    commands.getoutput("$SCHRODINGER/run split_structure.py -many_files -m %s %s %s"%(part, complex_file, out_split))
    out_receptor = os.path.splitext(out_split)[0] + "_receptor1"+ os.path.splitext(out_split)[1]
    if os.path.isfile(out_receptor):
        return out_receptor 
    else:
        return False

def prepare_protein (protein_file, prepared_protein, sleep_time = 300):
    #here the prepared protein should has ".mol2" as extension
    #commands.getoutput("$SCHRODINGER/utilities/prepwizard %s %s"%(protein_file, prepared_protein))
    with open('chimeraPrep.py','wb') as of:
        of.write(chimera_prep_text) 
    commands.getoutput('chimera --nogui --script "chimeraPrep.py %s %s" >& chimeraProtPrep.out' %(protein_file, prepared_protein))
    #time.sleep(sleep_time) 
    if os.path.isfile(prepared_protein):
        return True
    else:
        return False


def main_proteinprep (challenge_data_path, pdb_protein_path, working_folder ):
    os.chdir(working_folder)
    current_dir_layer_1 = os.getcwd()
#     all_stage_2_out = glob.glob("%s/*.txt"%challenge_data_path)
#     summary_file = "%s/summary.txt"%challenge_data_path
#     if summary_file in all_stage_2_out:
#         all_stage_2_out.remove(summary_file)
#     for single_stage_2_out in all_stage_2_out: 
#         target_id = os.path.basename(single_stage_2_out).split(".txt")[0]
#         valid_candidates[target_id] = []
#         if not os.path.isdir(target_id):
#             os.mkdir(target_id)
#         os.chdir(target_id)
#     #+++++++++++++++++++++
#     #get the infromation from stage 2 output
#         commands.getoutput("cp %s ." %(single_stage_2_out))
#         query_dic = extract_info_from_s2(target_id + ".txt")
# 
#     ######################
#     #step 1, check if there is a protein start with largest if not then don't need to continue
#     ######################
#         if not "largest" in query_dic:
#             logging.info("For this target protein: %s, there is no protein sharing the largest ligand witt. Not able to generate Docking grid, pass for this case..."%target_id)
#             os.chdir(current_dir_layer_1)     
#             continue
#         elif len(query_dic["largest"]) != 2:
#             logging.info("For this target protein: %s, the laregest protein has wrong number of informations associate with this id..."%target_id)
#             os.chdir(current_dir_layer_1)
#             continue
#         elif not "inchi" in query_dic:
#             logging.info("For this target protein: %s, there is no inchi info for the ligand..."%target_id)
#             os.chdir(current_dir_layer_1)
#             continue
#         else:
#             logging.info("============Start to work in this target protein: %s============"%target_id)
#             #raw_input()
#         ######################
#         #step 2, if there is a largest protein then copy this portein to this folder and generate the center of the ligand
#         ######################
#             largest_candidate_id = query_dic["largest"][0]
#             largest_candidate_filename = "largest-%s_%s.pdb" %(target_id, largest_candidate_id)
#             largest_pdb_folder_name = largest_candidate_id[1:3]
#             largest_ent_file = "pdb" + largest_candidate_id  + ".ent"
#             largest_pdbloc = os.path.join(pdb_protein_path, largest_pdb_folder_name, largest_ent_file)
#             if not os.path.isfile(largest_pdbloc):
#                 logging.info("Unable to find the ent file associate with the largest candidate pdb: %s at location %s"%(largest_candidate_id, largest_pdbloc)) 
#                 os.chdir(current_dir_layer_1)
#                 continue
#             else:
#                 commands.getoutput("cp %s %s"%(largest_pdbloc, largest_candidate_filename))
#                 valid_candidates[target_id].append(largest_candidate_filename)
# 
#         ######################
#         #step 3, get the center of the ligand in the largest pdb
#         ######################
#         try:
#             largest_ligand = query_dic["largest"][1] 
#         except:
#             logging.info("There is no ligand information for this largest candidate protein: %s"%(largest_candidate_id))
#             os.chdir(current_dir_layer_1)
#             continue
#         ligand_center = get_center (largest_candidate_filename, largest_ligand) 
#         if not ligand_center:
#             logging.info("Unable to find the center of the ligand for the largest candidate pdb: %s"%(largest_candidate_id))
#             os.chdir(current_dir_layer_1)
#             continue
#         else:
#             center_file = open("center.txt", "w")
#             center_file.writelines(ligand_center)
#             center_file.close()
#         ######################
#         #step 4, prepare the ligand 
#         ######################
#         #a. generate the smile string from inchi 
#         ligand_inchi = "InChI=" + query_dic["inchi"]
#         inchi_f = open("tmp.inchi", "w")
#         inchi_f.writelines(ligand_inchi)
#         inchi_f.close()
#         inchi_filename = "tmp.inchi"
#         smile_filename = "tmp.smi"
#         #print "babel -iinchi %s  -osmi ---errorlevel 1"%inchi_filename
#         commands.getoutput("babel -iinchi %s  -osmi %s ---errorlevel 1"%(inchi_filename, smile_filename))
#         #raw_input()
#         if os.path.isfile(smile_filename):
#             smile_file = open(smile_filename, "r")
#             ligand_smile = smile_file.readlines()
#             smile_file.close()
#         else:
#             logging.info( "Convert from inchi:%s to SMILES failed"%(ligand_inchi))
#         #finish generating the smiles, then try to prepared the ligand 
#         ##############ligand prep step starts here##############
#         #if not ligand_prepare(ligand_smile, "ligand.mae"):
#         if not ligand_prepare(smile_filename, "ligand.mae"):
#             logging.info("Unable to prepare the ligand for this query protein:%s"%target_id)
#             os.chdir(current_dir_layer_1)
#             continue 
#         else:
#         ########################################################
#         #step 5, align all proteins
#             for method_type in ("smallest", "holo", "apo"):
#                 if method_type in query_dic:
#                     #copy to here
#                     if len(query_dic[method_type]) == 2:
#                         #have both id and ligand info
#                         method_type_id = query_dic[method_type][0]
#                     else:
#                         #have only id info 
#                         method_type_id = query_dic[method_type]
#                     ## The pdb database is sorted by the middle two characters of the pdb code
#                     method_type_folder_name = method_type_id[1:3]
#                     method_ent_file = "pdb" + method_type_id  + ".ent"
#                     method_pdbloc = os.path.join(pdb_protein_path, method_type_folder_name, method_ent_file)
#                     if not os.path.isfile(method_pdbloc):
#                         logging.info("Unable to find the ent file associate with the %s pdb with ID: %s at location %s"%(method_type, method_type_id, largest_pdbloc))
#                         os.chdir(current_dir_layer_1)
#                         continue
#                     else:
#                         method_type_filename = "%s-%s_%s.pdb" %(method_type, target_id, method_type_id)
#                         commands.getoutput("cp %s %s"%(method_pdbloc, method_type_filename))
#                         valid_candidates[target_id].append(method_type_filename)
#                     align_proteins (largest_candidate_filename, method_type_filename, method_type_filename)

 
    ## Get all potential target directories and candidates within
    valid_candidates = {}
    #target_ligands = {}
    pot_target_dirs = list(os.walk(challenge_data_path))[0][1]
    #target_ids = []
    # Ensure that the directories are valid
    for pot_target_id in pot_target_dirs:
        os.chdir(current_dir_layer_1)
        # Does it look like a pdb id?
        if len(pot_target_id) != 4:
            logging.info('Filtering potential target directories: %s is not 4 characters long. Skipping' %(pot_target_id))
            continue
        commands.getoutput('mkdir %s' %(pot_target_id))
        #target_ids.append(pot_target_dir)
        valid_candidates[pot_target_id] = []
        target_dir_path = os.path.join(challenge_data_path, pot_target_id)

        # Pull in the ligand inchi
        lig_smiles_files = glob.glob('%s/lig_*.smi' %(target_dir_path))
        if len(lig_smiles_files) != 1:
            logging.info('Unable to find unambiguous ligand smiles for %s - glob returned %r' %(pot_target_id, lig_smiles_files))
            continue
        lig_smiles_file = lig_smiles_files[0]
        local_smiles_file = os.path.basename(lig_smiles_file)
        dest_smiles_file = os.path.join(pot_target_id, local_smiles_file)
        commands.getoutput('cp %s %s' %(lig_smiles_file, dest_smiles_file))
        
        # Copy in each valid candidate
        for candidate_file in glob.glob('%s/*-%s_*.pdb' %(target_dir_path, pot_target_id)):
            # The largest ligand will be in a pdb file called something like celpp_week19_2016/1fcz/largest-1fcz_1fcz-156-lig.pdb
            # We want to make sure we don't treat this like a receptor
            if 'lig.pdb' in candidate_file:
                continue
            commands.getoutput('cp %s %s' %(candidate_file, pot_target_id))
            candidate_local_file = os.path.basename(candidate_file)
            valid_candidates[pot_target_id].append((local_smiles_file, candidate_local_file))
                
    for target_id in valid_candidates.keys():
        os.chdir(target_id)

        ######################
        #step 6, prepare all proteins
        ######################
        for smiles_filename, candidate_filename in valid_candidates[target_id]:
            # Prepare the ligand
            if not ligand_prepare(smiles_filename, smiles_filename.replace('.smi','_prepped.mol2')):
                logging.info("Unable to prepare the ligand for this query protein:%s"%target_id)
                #os.chdir(current_dir_layer_1)
                continue 

            # Split the complex first
            candidate_prefix = candidate_filename.replace('.pdb','')
            out_split = candidate_prefix+ "_split.pdb"
            out_receptor = split_complex("pdb", candidate_filename, out_split)
            if not out_receptor:
                logging.info("Unable to split this protein:%s"%(candidate_filename))
                #os.chdir(current_dir_layer_1)
                continue
            
            logging.info("Successfully split this protein:%s, go to preparation step"%(candidate_filename))
            prepared_protein_mol2 = candidate_prefix + "_prepared.mol2"
            #pass the wizard sleep time here
            preparation_result = prepare_protein(out_receptor,prepared_protein_mol2, 180 )
            if not preparation_result:
                logging.info("Unable to prepare this protein:%s"%(out_split))
                #os.chdir(current_dir_layer_1)
                continue
            #convert into pdb format
            out_prepare_pdb = candidate_prefix + "_prepared.pdb"
            commands.getoutput("$SCHRODINGER/utilities/pdbconvert -imae %s -opdb %s"%(prepared_protein_mol2, out_prepare_pdb))
            logging.info("Successfully prepared this protein:%s"%(out_prepare_pdb))
        os.chdir(current_dir_layer_1)
                        
                

if ("__main__") == (__name__):
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("-p", "--pdbdb", metavar = "PATH", help = "PDB DATABANK which we will dock into")
    parser.add_argument("-c", "--candidatedir", metavar="PATH", help = "PATH where we could find the stage 2 output")
    parser.add_argument("-o", "--outdir", metavar = "PATH", help = "PATH where we run stage 3")
    #parser.add_option("-s", "--sleep", metavar = "VALUE", help = "Sleep time for protein prep")
    #parser.add_option("-u", "--update", default = False, action = "store_true", help = "update the protein generation and docking step")
    logger = logging.getLogger()
    logging.basicConfig( format  = '%(asctime)s: %(message)s', datefmt = '%m/%d/%y %I:%M:%S', filename = 'final.log', filemode = 'w', level   = logging.DEBUG )
    opt = parser.parse_args()
    pdb_location = opt.pdbdb
    challenge_data_path = opt.candidatedir
    result_path = opt.outdir
    #sleep_time = opt.sleep
    #running under this dir
    running_dir = os.getcwd()
    main_proteinprep(challenge_data_path, pdb_location, result_path)
    #move the final log file to the result dir
    log_file_path = os.path.join(running_dir, 'final.log')
    commands.getoutput("mv %s %s"%(log_file_path, result_path))

