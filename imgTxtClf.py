import time
start = time.time()
import numpy as np
import os
import re
import sys
import csv
import math
import itertools
from time import strftime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC #LinearSVC
import matplotlib.pyplot as plt
import cv2
from sklearn.cross_validation import *
from scipy.cluster.vq import *
from sklearn.preprocessing import StandardScaler
from sklearn.externals import joblib
import random
from sklearn.metrics import roc_curve,f1_score,auc
from scipy import interp

'''
USAGE: python2 imgTxtClf.py /path/to/text /path/to/images
pulls only files that have both an image and text for sanitization
'''

'''GLOBALS'''
#precision of ROC plots
fpr_space = np.linspace(0, 1, 100)
#image clusters
imgVoc = 100
#test size #SET TO NONE FOR FULL SET
testSize = 2000
#number of folds for cv
nFolds = 10
''''''

def main(txtPath, imgPath):
    
    names = [os.path.splitext(i)[0] for i in os.listdir(imgPath) if '.jpg' in i]    
    
    random.shuffle(names)
    
    ###TEST FOR SMALER SUBSETS###
    if testSize is not None:
        names = [random.choice(names) for i in range(0,testSize)]
    #############################  

    #regex to find class, divided into the same sublistings
    pattern=re.compile(r"([0-9]+)-")
    img,txt,cls = [],[],[]
    cite_high = 10 #divider for high vs low citations

    #split papers into high vs low cited True = high, False = low
    for f in names:
        
        cites=pattern.search(f)
        if cites:
            if int(cites.group(1)) >= cite_high: 
                cls.append(True) 
            else: 
                cls.append(False)
        else: 
            print(f)
            print("WARNING: file name not formatted correctly. giving up.")
            exit()
        txt.append(os.path.join(txtPath,f)+".pdf.txt")
        img.append(os.path.join(imgPath,f)+".jpg")

    #define stratified crosss validation scheme
    skf = StratifiedKFold(cls, n_folds=nFolds, shuffle=True)

    '''main k-fold cross validation loop'''
    print 'Performing %s fold cross validation' %nFolds
    txtF1,imgF1,txtConfs,imgConfs,txtRocs,imgRocs = [],[],[],[],[],[]
    clsShuffled, namesShuffled= [],[] 
    txt_mean_tpr,img_mean_tpr = 0,0
    fpr_space = np.linspace(0, 1, 100)
    
    count = 0
    
    for train_index, test_index in skf:
        count += 1
        plt.figure()        
        
        #print some stuff about data split then split it        
        print '\n*******Fold %s********' %count
        #print "TRAIN: %s" %train_index, "\nTEST: %s" %test_index 
        IMG_train, IMG_test = [img[i] for i in train_index], [img[i] for i in test_index]
        TXT_train, TXT_test = [txt[i] for i in train_index], [txt[i] for i in test_index]
        cls_train, cls_test = [cls[i] for i in train_index], [cls[i] for i in test_index]    
        
        #keep track of order of filenames and class for metaclassifier
        clsShuffled.append(cls_test)
        namesShuffled.append(IMG_test)

        '''text classifier'''
        #extract features & train
        txtExtract=TfidfVectorizer(input='filename',stop_words='english')
        print 'extracting text features'
        TXT_feat=txtExtract.fit_transform(TXT_train+TXT_test)
        TXT_train_feat=TXT_feat[:len(TXT_train)]
        TXT_test_feat=TXT_feat[-len(TXT_test):]
        print 'training text classifier'
        txtClf=SVC(kernel='linear', probability=False, random_state = random.randint(0,10000))
        txtClf.fit(TXT_train_feat,cls_train)

        #save the text clf
        #joblib.dump((txtClf, TXT_train_feat, TXT_test_feat, cls_train, cls_test), "txtClf.pkl", compress=3)    
        
        #get confidence and build roc curve
        txtConfs.append(txtClf.decision_function(TXT_test_feat))
        txtPredictions = txtClf.predict(TXT_test_feat)
        fpr, tpr, thresholds = roc_curve(cls_test,txtConfs[count-1])
        txt_mean_tpr += interp(fpr_space, fpr, tpr)
        txt_mean_tpr[0] = 0
        txt_auc = auc(fpr, tpr)
        plotROC(fpr,tpr,txt_auc,'Text fold %d' %count)
           
        
        fMeasure = f1_score(cls_test, txtPredictions)
        #append to overall list        
        txtRocs.append([fpr, tpr, thresholds])
        txtF1.append(fMeasure)
        
        '''image classifier'''
        imgClf=SVC(kernel='rbf', probability=False, random_state = random.randint(0,10000))
        #extract features & train
        IMG_feat=imgFeatExtract(IMG_train+IMG_test,None)
        IMG_train_feat=[IMG_feat[0][:len(IMG_train)],IMG_feat[1]]
        IMG_test_feat=[IMG_feat[0][-len(IMG_test):],IMG_feat[1]]
        print 'training image classifier'       
        imgClf.fit(IMG_train_feat[0],cls_train)

        #get confidence and build roc curve
        imgConfs.append(imgClf.decision_function(IMG_test_feat[0]))
        imgPredictions = imgClf.predict(IMG_test_feat[0])
        fpr, tpr, thresholds = roc_curve(cls_test,imgConfs[count-1])
        img_mean_tpr += interp(fpr_space, fpr, tpr)
        img_mean_tpr[0] = 0
        img_auc = auc(fpr, tpr)
        plotROC(fpr,tpr,img_auc,'Image fold %d' %count)
        plt.show()        
        
        fMeasure = f1_score(cls_test, imgPredictions)
        #append to overall list        
        imgRocs.append([fpr, tpr, thresholds])
        imgF1.append(fMeasure)
        
    '''calculate results'''
    txt_mean_F1 = sum(txtF1)/len(txtF1)
    txt_mean_tpr /= nFolds
    txt_mean_tpr[-1] = 1.0
    txt_mean_auc = auc(fpr_space, txt_mean_tpr)
    
    img_mean_F1 = sum(imgF1)/len(imgF1)
    img_mean_tpr /= nFolds
    img_mean_tpr[-1] = 1.0
    img_mean_auc = auc(fpr_space, img_mean_tpr)
    
    joblib.dump((imgClf, txtClf, txtConfs, imgConfs, clsShuffled, namesShuffled, txt_mean_auc, img_mean_auc, txt_mean_F1, txt_mean_tpr, img_mean_F1, img_mean_tpr), "n2000k100cv10.pkl", compress=3)    
    
    '''meta classifier'''
    meta_mean_F1, meta_mean_tpr, meta_mean_auc = metaClf(txtConfs, imgConfs, clsShuffled, namesShuffled, txt_mean_auc, img_mean_auc)

    
    print '*******Output*******'
    
    print '\nText:'
    print 'F1 Score: %s' %txt_mean_F1
    print 'AUC: %s' %txt_mean_auc
    
    print '\nImages:'
    print 'F1 Score: %s' %img_mean_F1
    print 'AUC: %s' %img_mean_auc

    print '\nCombined:'
    print 'F1 Score: %s' %meta_mean_F1
    print 'AUC: %s' %meta_mean_auc
    
    plt.figure()
    plotROC(fpr_space,txt_mean_tpr,txt_mean_auc,'Text')
    plotROC(fpr_space,img_mean_tpr,img_mean_auc,'Image')
    plotROC(fpr_space,meta_mean_tpr,meta_mean_auc,'Combined')
    plt.show()
    
    #save TPR's to CSV for plotting ROC elsewhere
#    time = strftime("%Y-%m-%d_%H:%M:%S")
#    txt = csv.writer(open("txt_tpr_%s.csv" %time, "wb"))
#    txt.writerow(txt_mean_tpr)
#    img = csv.writer(open("img_tpr_%s.csv" %time, "wb"))
#    img.writerow(img_mean_tpr)
#    ti = csv.writer(open("ti_tpr_%s.csv" %time, "wb"))
#    ti.writerow(ti_mean_tpr)

    print 'Function time:', time.time()-start, 'seconds.'
    
#take a list of image file names and transform them into a feature matrix. 
#returns tuple with the matrix first, vocab second.
def imgFeatExtract(image_paths, inVoc):
    # Create feature extraction and keypoint detector objects
    sift = cv2.SIFT()

    # Extract features, combine with image storage location
    print 'extracting image features'
    des_list = []
    for image_path in image_paths:
        if ".jpg" in image_path:
            im = cv2.imread(image_path, cv2.IMREAD_COLOR)
            kpts, des = sift.detectAndCompute(im, None)
            des_list.append((image_path, des))

    # Stack all the descriptors vertically in a numpy array
    descriptors = des_list[0][1]
    for image_path, descriptor in des_list[1:]:
        if ".jpg" in image_path:
            descriptors = np.vstack((descriptors, descriptor))

    k=imgVoc

    if inVoc is None: #so that we can build vocab or not
        # build vocabulary with k-means clustering
        #vocabulary = centroids
        print('performing image feature clustering K=%s' %k)
        voc, variance = kmeans(descriptors, k, 1) #voc = visual vocabulary
    else: voc=inVoc

    # Calculate frequency vector
    print('creating img frequency vector')
    im_features = np.zeros((len(image_paths), k), "float32")
    for i in xrange(len(image_paths)):
        if ".jpg" in image_path:
            words, distance = vq(des_list[i][1],voc)
            for w in words:
                im_features[i][w] += 1

    # Standardization for input ot linear classifier
    print('standardizing img input for classification')
    stdSlr = StandardScaler().fit(im_features)
    im_features = stdSlr.transform(im_features)
    
    #save image classifier
    joblib.dump((clf, training_names, stdSlr, k, voc), "imgclf.pkl", compress=3)    

    return(im_features,voc)

#metaclassifier trained on probability of the txt and img classifier's inputs
def metaClf(txtConfs, imgConfs, clsShuffled, namesShuffled, txt_mean_auc, img_mean_auc):
    
    #flatten lists, maintain correct order
    txtConfs = list(itertools.chain(*txtConfs))
    imgConfs = list(itertools.chain(*imgConfs))
    clsShuffled = list(itertools.chain(*clsShuffled))
    namesShuffled = list(itertools.chain(*namesShuffled))
    
    txt_auc_sqrt = math.pow(txt_mean_auc, 1/2)
    img_auc_sqrt = math.pow(img_mean_auc, 1/2)
    
    txtConfs_wtd = [i*txt_auc_sqrt for i in txtConfs]
    imgConfs_wtd = [i*img_auc_sqrt for i in imgConfs]

    #arrange txt and img confidences as features for the meta clf
    #and weight the confidences by the auc
    tiConfs = np.vstack((txtConfs_wtd,imgConfs_wtd))
    tiConfs = np.transpose(tiConfs)

    skf = StratifiedKFold(clsShuffled, n_folds=nFolds, shuffle=True)

    count = 0
    namesReshuffled = []
    metaRocs,metaF1,metaConfs = [],[],[]
    meta_mean_tpr = 0
    
    for train_index, test_index in skf:
        count += 1
        plt.figure()        

        #print some stuff about data split then split it        
        print '\nTraining Meta Classifier'        
        print '*******Fold %s********' %count
        META_train, META_test = [tiConfs[i] for i in train_index], [tiConfs[i] for i in test_index]
        cls_train, cls_test = [clsShuffled[i] for i in train_index], [clsShuffled[i] for i in test_index]
        namesReshuffled.append([namesShuffled[i] for i in test_index]) #keep track of reshuffled filenames

        #train the metaclassifier
        metaClf=SVC(kernel='rbf', probability=False, random_state = random.randint(0,10000))
        metaClf.fit(META_train,cls_train)
        
        #get confidence and build roc curve
        metaPredictions = metaClf.predict(META_test)
        metaConfs.append(metaClf.decision_function(META_test))
        fpr, tpr, thresholds = roc_curve(cls_test,metaConfs[count-1])
        meta_mean_tpr += interp(fpr_space, fpr, tpr)
        meta_mean_tpr[0] = 0
        meta_auc = auc(fpr, tpr)
        plotROC(fpr,tpr,meta_auc,'Meta Clf fold %d' %count)

        fMeasure = f1_score(cls_test, metaPredictions)
        #append to overall list        
        metaRocs.append([fpr, tpr, thresholds])
        metaF1.append(fMeasure)
    
    plt.show()
    meta_mean_F1 = sum(metaF1)/len(metaF1)
    meta_mean_tpr /= nFolds
    meta_mean_tpr[-1] = 1.0
    meta_mean_auc = auc(fpr_space, meta_mean_tpr)

    return meta_mean_F1, meta_mean_tpr, meta_mean_auc
        
    
#function to plot ROC curve
def plotROC(mean_fpr, mean_tpr, mean_auc, feature_type):
    
    #plt.figure()
    plt.plot(mean_fpr, mean_tpr,label='%s ROC (area = %0.2f)' %(feature_type, mean_auc), lw=2)
    plt.plot([0, 1], [0, 1], '--', color=(0.6, 0.6, 0.6))#, label='Luck')
    plt.xlim([-0.05, 1.05])
    plt.ylim([-0.05, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('%s Receiver operating characteristic plot' %feature_type)
    plt.legend(loc="lower right")
    #plt.show()
    
#main(sys.argv[1], sys.argv[2]) #for running from command line
main(txtPath, imgPath) #for running from IDE