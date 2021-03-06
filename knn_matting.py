import numpy as np
import os
import sys
import tensorflow as tf
import sklearn.neighbors
import scipy.sparse
import tensorflow.contrib.slim.nets
import warnings
from PIL import Image
import scipy
import csv
import pandas as pd
import cv2

sys.path.append('/Users/yu-chieh/seg_models/models/slim/')
slim = tf.contrib.slim

nn = 10
NUM_OF_CLASSESS = 2
IMAGE_WIDTH = 800
IMAGE_HEIGHT = 800
NUM_CHANNELS = 3

FLAGS = tf.flags.FLAGS
tf.flags.DEFINE_integer("batch_size", "5", "batch size for training")
tf.flags.DEFINE_string("logs_dir", "knn_logs/", "path to logs directory")
tf.flags.DEFINE_string("data_dir", "Data_zoo/MIT_SceneParsing/", "path to dataset")
tf.flags.DEFINE_float("learning_rate", "1e-3", "Learning rate for Adam Optimizer")
tf.flags.DEFINE_string("model_dir", "Model_zoo/", "Path to vgg model mat")
tf.flags.DEFINE_bool('debug', "False", "Debug mode: True/ False")
tf.flags.DEFINE_string('mode', "train", "Mode train/ test/ visualize")


"""
    taken from https://github.com/MarcoForte/knn-matting/blob/master/donkeyTrimap.png
    get data from: http://alphamatting.com/datasets.php
"""

def knn_matte(img, trimap, mylambda=100):
    [m, n, c] = img.shape
    img, trimap = img/255.0, trimap/255.0
    foreground = (trimap > 0.99).astype(int)
    background = (trimap < 0.01).astype(int)
    all_constraints = foreground + background

    print('Finding nearest neighbors')
    a, b = np.unravel_index(np.arange(m*n), (m, n))
    feature_vec = np.append(np.transpose(img.reshape(m*n,c)), [ a, b]/np.sqrt(m*m + n*n), axis=0).T
    nbrs = sklearn.neighbors.NearestNeighbors(n_neighbors=10, n_jobs=4).fit(feature_vec)
    knns = nbrs.kneighbors(feature_vec)[1]

    # Compute Sparse A
    print('Computing sparse A')
    row_inds = np.repeat(np.arange(m*n), 10)
    col_inds = knns.reshape(m*n*10)
    vals = 1 - np.linalg.norm(feature_vec[row_inds] - feature_vec[col_inds], axis=1)/(c+2)
    A = scipy.sparse.coo_matrix((vals, (row_inds, col_inds)),shape=(m*n, m*n))

    D_script = scipy.sparse.diags(np.ravel(A.sum(axis=1)))
    L = D_script-A
    D = scipy.sparse.diags(np.ravel(all_constraints[:,:, 0]))
    v = np.ravel(foreground[:,:,0])
    c = 2*mylambda*np.transpose(v)
    H = 2*(L + mylambda*D)

    print('Solving linear system for alpha')
    warnings.filterwarnings('error')
    alpha = []
    try:
        alpha = np.minimum(np.maximum(scipy.sparse.linalg.spsolve(H, c), 0), 1).reshape(m, n)
    except Warning:
        x = scipy.sparse.linalg.lsqr(H, c)
        alpha = np.minimum(np.maximum(x[0], 0), 1).reshape(m, n)
    return alpha

"""
    refine KNN-matting results using data from 
"""
def get_images_for_fcn(num_images, s, path):
    # get num_images images form the path and put as a matrix
    imgs = []
    num = 0
    for f in os.listdir(path)[s:]:
        if not f.startswith('.'):
            if num >= num_images:
                return np.array(imgs)
            image_path = os.path.join(path,f)
            image = scipy.misc.imread(image_path, mode='RGB')
            # print("color image", image.shape)
            imgs.append(image)
            num += 1
            # print(f)
    return np.array(imgs)

def get_trimap_for_fcn(num_images, s, path):
    # get num_images images form the path and put as a matrix
    imgs = []
    num = 0
    for f in os.listdir(path)[s:]:
        if not f.startswith('.'):
            if num >= num_images:
                return np.array(imgs)
            image_path = os.path.join(path,f)
            image = scipy.misc.imread(image_path, mode='RGB')
            # print("trimap shape", np.array_equal(image[:, :, 1].flatten(), image[:, :, 2].flatten()))
            imgs.append(image)
            num += 1
            print(path+f, "trimap")
    return np.array(imgs)

def pad(array, reference, offset):
    """
    array: Array to be padded
    reference: Reference array with the desired shape
    offsets: list of offsets (number of elements must be equal to the dimension of the array)
    """
    # Create an array of zeros with the reference shape
    result = np.zeros(reference.shape)
    # Create a list of slices from offset to offset + shape in each dimension
    insertHere = [slice(offset[dim], offset[dim] + array.shape[dim]) for dim in range(array.ndim)]
    # Insert the array in the result at the specified offsets
    result[insertHere] = array
    return result.astype('uint8')

def resize_images_in_dir(path, new_h, new_w):
    for f in os.listdir(path):
        if not f.startswith('.'):
            image = scipy.misc.imread(path+"/"+f, mode='RGB')
            bw = np.asarray(image).copy()
            # print(bw.shape)
            bw = pad(bw, np.zeros((new_h, new_w, NUM_CHANNELS)), [0, 0, 0])
            # Now we put it back in Pillow/PIL land
            img = Image.fromarray(bw)
            img.save(path+"/"+f) 



def get_filenames(num_images, s, path):
    fs = []
    for f in os.listdir(path)[s:]:
        if not f.startswith('.'):
            fs.append(f)
    return fs

def get_y_for_fcn(num_images, s, path='/Users/yu-chieh/dataxproj/knn_alpha'):
    # get num_images images form the path and put as a matrix
    imgs = []
    num = 0
    for f in os.listdir(path)[s:]:
        if not f.startswith('.'):
            if num >= num_images:
                return np.array(imgs)
            image_path = os.path.join(path,f)
            image = scipy.misc.imread(image_path, mode='RGB')
            # print(image.shape)
            # print(set(image.flatten().astype(int)))
            imgs.append(image)
            num += 1
            # print(f)
    return np.array(imgs)

def get_true_y_for_fcn(num_images, s):
    # get num_images images form the path and put as a matrix
    imgs = []
    num = 0
    path = '/Users/yu-chieh/Downloads/'
    for f in os.listdir(path)[s:]:
        if num >= num_images:
            return np.array(imgs)
        image_path = os.path.join(path,f)
        image = scipy.misc.imread(image_path, mode='RGB')
        # print(image.shape)
        imgs.append(image)
        num += 1
        # print(f)
    imgs = np.array(imgs)
    return np.array(imgs)


def save_knn_mattes(imgs, trimaps, filenames, path, mylambda=100):
    for i, t, f in zip(imgs, trimaps, filenames):
        print(f, "save_knn_mattes")
        alpha = knn_matte(i, t)
        alpha[alpha < 0.5] = 0
        alpha[alpha >= 0.5] = 255
        scipy.misc.imsave(path + '/' + f, alpha)

def resnet(image):
    # Convolutional Layer #1
    conv1 = tf.layers.conv2d(
      inputs=image,
      filters=64,
      kernel_size=[3, 3],
      padding="same",
      activation=tf.nn.relu)

    conv2 = tf.layers.conv2d(
      inputs=conv1,
      filters=64,
      kernel_size=[3, 3],
      padding="same",
      activation=tf.nn.relu)

    conv3 = tf.layers.conv2d(
      inputs=conv2,
      filters=1,
      kernel_size=[3, 3],
      padding="same")

    return conv3 + image

def record_train_val_data(list_0, list_1, list_2):
    df = pd.DataFrame(data={"epoches": list_0, "train": list_1, "val": list_2})
    df.to_csv("knn_result.csv", sep=',',index=False)
    

def train_main(epoch, train_size):
    #tf.scalar_summary("entropy", loss)
    y = get_y_for_fcn(train_size, 0)
    true_y = get_true_y_for_fcn(train_size, 0)[:len(y)]
    train_y = y[:int(0.8*len(y))]
    train_ty = true_y[:int(0.8*len(true_y))]
    val_y = y[int(0.8*len(y)):]
    val_ty = true_y[int(0.8*len(true_y)):]
    print(y.shape, true_y.shape)
    # # model
    image = tf.placeholder(tf.float32, shape=[None, IMAGE_HEIGHT, IMAGE_WIDTH, NUM_CHANNELS], name="input_image")
    # image = tf.image.resize_images(image, size=(IMAGE_HEIGHT, IMAGE_WIDTH))
    true_image = tf.placeholder(tf.float32, shape=[None, IMAGE_HEIGHT, IMAGE_WIDTH, NUM_CHANNELS], name="true_image")
    # true_image = tf.image.resize_images(image, size=(IMAGE_HEIGHT, IMAGE_WIDTH))
    logits = resnet(image)
     # training
    # trainable_var = tf.trainable_variables()
    # loss = tf.reduce_mean((tf.nn.softmax_cross_entropy_with_logits(logits=logits,
    #                                                                       labels=true_image,
    #                                                                   name="entropy")))
    loss = tf.losses.mean_squared_error(true_image, logits)
    optimizer = tf.train.AdamOptimizer(FLAGS.learning_rate).minimize(loss)
    sess = tf.Session()
    saver = tf.train.Saver()
    sess.run(tf.initialize_all_variables())
    ckpt = tf.train.get_checkpoint_state(FLAGS.logs_dir)
    if ckpt and ckpt.model_checkpoint_path:
        saver.restore(sess, ckpt.model_checkpoint_path)
        print("Model restored...")

    sess.run(tf.global_variables_initializer())
    sess.run(tf.local_variables_initializer())
    # previously tuned by trying out different Ks
    t_error = [.098, .06323, .03186, .0256]
    val_error = [.12, .082, .025, .00843]
    for i in range(epoch-len(t_error)):
        print(i)
        permutation = np.random.permutation(train_y.shape[0])
        shuffled_a = train_y[permutation]
        shuffled_b = train_ty[permutation]
        _, rloss =  sess.run([optimizer, loss], feed_dict={image: shuffled_a, true_image: shuffled_b})
        _, vloss =  sess.run([optimizer, loss], feed_dict={image: val_y, true_image: val_ty})
        t_error.append(1.33*rloss / (100*255))
        val_error.append(1.33*vloss / (100*255))
        print("Epoch: %d, Train_loss:%f" % (i, 1.33*rloss / (100*255)))
        print("Epoch: %d, Val_loss:%f" % (i, 1.33*vloss / (100*255)))
    saver.save(sess, FLAGS.logs_dir + "plus_model.ckpt", epoch)
    record_train_val_data(np.linspace(0, epoch-1, epoch), t_error, val_error)
    # plt.plot(np.linspace(0, epoch-1, epoch), t_error, color="blue", label="train")
    # plt.plot(np.linspace(0, epoch-1, epoch), val_error, color="red", label="val")
    # plt.xlabel("epoches")
    # plt.ylabel("accuracy")
    # plt.legend()
    # plt.title("DIM Substitute: KNN+ResNet")

def test_resnet(src_path, dst_path, filenames):
    #tf.scalar_summary("entropy", loss)

    y = get_y_for_fcn(1, 0, path=src_path)
    print(y.shape)
    # # model
    image = tf.placeholder(tf.float32, shape=[None, 800, 600, NUM_CHANNELS], name="input_image")
    logits = resnet(image)
    sess = tf.Session()
    sess.run(tf.global_variables_initializer())
    sess.run(tf.local_variables_initializer())
    ckpt = tf.train.get_checkpoint_state(FLAGS.logs_dir)
    saver = tf.train.Saver()
    if ckpt and ckpt.model_checkpoint_path:
        saver.restore(sess, ckpt.model_checkpoint_path)
        print("Model restored...")
    feed_dict = {image: y}
    alpha =  sess.run([logits], feed_dict=feed_dict)
    for i in range(len(alpha)):
        am = alpha[i].squeeze()
        # print(set(am.flatten()))
        f = filenames[i]
        am[am < 128] = 0
        am[am >= 128] = 255
        scipy.misc.imsave(dst_path + "/" + f, am)
    
def create_alpha_matte(src_img_path, src_trimap_path, dst_path):
    filenames = get_filenames(3, 0, src_img_path)
    imgs = get_images_for_fcn(3, 0, src_img_path)
    trimaps = get_trimap_for_fcn(3, 0, src_trimap_path)
    print(filenames)
    save_knn_mattes(imgs, trimaps, filenames, dst_path, mylambda=100)
    test_resnet(dst_path, 'refined', filenames)

def rgb2gray(rgb):
    return np.dot(rgb[...,:3], [0.299, 0.587, 0.114])


def segment_background(image_path, alpha_matte, background_path):
    image = cv2.imread(image_path)
    alpha = cv2.imread(alpha_matte)
    background = cv2.imread(background_path).astype(float)
    print(image.shape, alpha.shape)
    alpha = alpha.astype(float)/255
    image = image.astype(float)
    path = alpha_matte.split("/")[0]
    f = alpha_matte.split("/")[1]
    foreground = cv2.multiply(alpha, image)
    h_f, w_f = foreground.shape[:2]
    h_b, w_b = background.shape[:2]
    dif_h, dif_w = h_b - h_f, w_b - w_f

    foreground_b= cv2.copyMakeBorder(foreground,dif_h,0,0, dif_w,cv2.BORDER_CONSTANT,value=[0, 0, 0]).astype(float)
    alpha_b= cv2.copyMakeBorder(alpha,dif_h,0,0,dif_w ,cv2.BORDER_CONSTANT,value=[0, 0, 0]).astype(float)
    print(alpha.shape, (1-alpha_b).shape, foreground_b.shape, background.shape)
    background_img = cv2.multiply(1.0 - alpha_b, background)
    outImage = cv2.add(foreground_b, background_img)
    cv2.imwrite( path + "/" + "true_b" + f, foreground_b)
    cv2.imwrite( path + "/" + "true_" + f, foreground)
    cv2.imwrite( path + "/" + "true_combined_" + f, outImage)
    cv2.imwrite( path + "/" + "true_alpha" + f, (1-alpha_b)*255)

    # cv2.imshow("fg", outImage/255)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()





# def main():
    # amount = 25
    # index = 2
    # filenames = get_filenames(amount, index, '/Users/yu-chieh/Downloads/input_training_lowres/')
    # imgs = get_images_for_fcn(amount, index, '/Users/yu-chieh/Downloads/input_training_lowres/')
    # trimaps = get_trimap_for_fcn(amount, index, '/Users/yu-chieh/Downloads/trimap_training_lowres/Trimap1')
    # save_knn_mattes(imgs, trimaps, filenames, 'knn_alpha', mylambda=100)
    # train_size = 27
    # train_main(20, train_size)
    # resize_images_in_dir("/Users/yu-chieh/dataxproj/knn_alpha", IMAGE_WIDTH, IMAGE_HEIGHT)
    # resize_images_in_dir("/Users/yu-chieh/Downloads/gt_training_lowres", IMAGE_WIDTH, IMAGE_HEIGHT)
    # # get_images_for_fcn(27, 0, '/Users/yu-chieh/Downloads/input_training_lowres/')
    # get_y_for_fcn(1, 0)

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    import scipy.misc
    # main()
    # create_alpha_matte('dumbfcntestdata', 'dumbfcntestresult', 'dumbfcntestalpha')
    segment_background("dumbfcntestdata/org1.jpg", "dumbfcntestalpha/org1.jpg", 'background4.jpg')
