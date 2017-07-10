import tensorflow as tf
import cuhk03_dataset

FLAGS = tf.flags.FLAGS
tf.flags.DEFINE_integer('batch_size', '2', 'batch size for training')
tf.flags.DEFINE_integer('max_steps', '100000', 'max steps for training')
tf.flags.DEFINE_string('logs_dir', 'logs/', 'path to logs directory')
tf.flags.DEFINE_string('data_dir', 'data/', 'path to dataset')
tf.flags.DEFINE_float('learning_rate', '0.0001', 'Learning rate for Adam Optimizer')
tf.flags.DEFINE_string('mode', 'train', 'Mode train/ val/ test')
tf.flags.DEFINE_string('images_dir', '', 'path to test images')

IMAGE_WIDTH = 60
IMAGE_HEIGHT = 160

def preprocess(images, is_train):
    split = tf.split(images, [1, 1])
    shape = [1 for _ in xrange(split[0].get_shape()[1])]
    def train():
        for i in xrange(len(split)):
            split[i] = tf.reshape(split[i], [FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3])
            split[i] = tf.image.resize_images(split[i], [IMAGE_HEIGHT + 8, IMAGE_WIDTH + 3])
            split[i] = tf.split(split[i], shape)
            for j in xrange(len(split[i])):
                split[i][j] = tf.reshape(split[i][j], [IMAGE_HEIGHT + 8, IMAGE_WIDTH + 3, 3])
                split[i][j] = tf.random_crop(split[i][j], [IMAGE_HEIGHT, IMAGE_WIDTH, 3])
                split[i][j] = tf.image.random_flip_left_right(split[i][j])
                split[i][j] = tf.image.random_brightness(split[i][j], max_delta=32. / 255.)
                split[i][j] = tf.image.random_saturation(split[i][j], lower=0.5, upper=1.5)
                split[i][j] = tf.image.random_hue(split[i][j], max_delta=0.2)
                split[i][j] = tf.image.random_contrast(split[i][j], lower=0.5, upper=1.5)
                split[i][j] = tf.image.per_image_standardization(split[i][j])
        return [tf.reshape(tf.concat(split[0], axis=0), [FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3]),
            tf.reshape(tf.concat(split[1], axis=0), [FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3])]
    def val():
        for i in xrange(len(split)):
            split[i] = tf.reshape(split[i], [FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3])
            split[i] = tf.image.resize_images(split[i], [IMAGE_HEIGHT, IMAGE_WIDTH])
            split[i] = tf.split(split[i], shape)
            for j in xrange(len(split[i])):
                split[i][j] = tf.reshape(split[i][j], [IMAGE_HEIGHT, IMAGE_WIDTH, 3])
                split[i][j] = tf.image.per_image_standardization(split[i][j])
        return [tf.reshape(tf.concat(split[0], axis=0), [FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3]),
            tf.reshape(tf.concat(split[1], axis=0), [FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3])]
    return tf.cond(is_train, train, val)

def network(images1, images2):
    with tf.variable_scope('network'):
        # Tied Convolution
        conv1_1 = tf.layers.conv2d(images1, 20, [5, 5], activation=tf.nn.relu, name='conv1_1')
        pool1_1 = tf.layers.max_pooling2d(conv1_1, [2, 2], [2, 2], name='pool1_1')
        conv1_2 = tf.layers.conv2d(pool1_1, 25, [5, 5], activation=tf.nn.relu, name='conv1_2')
        pool1_2 = tf.layers.max_pooling2d(conv1_2, [2, 2], [2, 2], name='pool1_2')
        conv2_1 = tf.layers.conv2d(images2, 20, [5, 5], activation=tf.nn.relu, name='conv2_1')
        pool2_1 = tf.layers.max_pooling2d(conv2_1, [2, 2], [2, 2], name='pool2_1')
        conv2_2 = tf.layers.conv2d(pool2_1, 25, [5, 5], activation=tf.nn.relu, name='conv2_2')
        pool2_2 = tf.layers.max_pooling2d(conv2_2, [2, 2], [2, 2], name='pool2_2')

        # Cross-Input Neighborhood Differences
        trans = tf.transpose(pool1_2, [0, 3, 1, 2])
        shape = trans.get_shape().as_list()
        m1s = tf.ones([shape[0], shape[1], shape[2], shape[3], 5, 5])
        reshape = tf.reshape(trans, [shape[0], shape[1], shape[2], shape[3], 1, 1])
        f = tf.multiply(reshape, m1s)

        trans = tf.transpose(pool2_2, [0, 3, 1, 2])
        shape = trans.get_shape().as_list()
        g = []
        for i in xrange(FLAGS.batch_size):
            for j in xrange(25):
                print(i, j)
                pad = tf.pad(trans[i][j], [[2, 2], [2, 2]])
                for y in xrange(shape[2]):
                    for x in xrange(shape[3]):
                        g.append(tf.slice(pad, [y, x], [5, 5]))

        concat = tf.concat(g, axis=0)
        g = tf.reshape(concat, [shape[0], shape[1], shape[2], shape[3], 5, 5])
        reshape1 = tf.reshape(tf.subtract(f, g), [shape[0], shape[1], shape[2] * 5, shape[3] * 5])
        reshape2 = tf.reshape(tf.subtract(g, f), [shape[0], shape[1], shape[2] * 5, shape[3] * 5])
        k1 = tf.nn.relu(tf.transpose(reshape1, [0, 2, 3, 1]), name='k1')
        k2 = tf.nn.relu(tf.transpose(reshape2, [0, 2, 3, 1]), name='k2')

        # Patch Summary Features
        l1 = tf.layers.conv2d(k1, 25, [5, 5], (5, 5), activation=tf.nn.relu, name='l1')
        l2 = tf.layers.conv2d(k2, 25, [5, 5], (5, 5), activation=tf.nn.relu, name='l2')

        # Across-Patch Features
        m1 = tf.layers.conv2d(l1, 25, [3, 3], activation=tf.nn.relu, name='m1')
        pool_m1 = tf.layers.max_pooling2d(m1, [2, 2], [2, 2], padding='same', name='pool_m1')
        m2 = tf.layers.conv2d(l2, 25, [3, 3], activation=tf.nn.relu, name='m2')
        pool_m2 = tf.layers.max_pooling2d(m2, [2, 2], [2, 2], padding='same', name='pool_m2')

        # Higher-Order Relationships
        concat = tf.concat([pool_m1, pool_m2], axis=3)
        reshape = tf.reshape(concat, [FLAGS.batch_size, -1])
        fc1 = tf.layers.dense(reshape, 500, tf.nn.relu, name='fc1')
        fc2 = tf.layers.dense(fc1, 2, name='fc2')

        return fc2

def main(argv=None):
    learning_rate = tf.placeholder(tf.float32, name='learning_rate')
    images = tf.placeholder(tf.float32, [2, FLAGS.batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, 3], name='images')
    labels = tf.placeholder(tf.float32, [FLAGS.batch_size, 2], name='labels')
    is_train = tf.placeholder(tf.bool, name='is_train')
    tarin_num_id = cuhk03_dataset.get_num_id(FLAGS.data_dir, 'train')
    val_num_id = cuhk03_dataset.get_num_id(FLAGS.data_dir, 'val')

    images1, images2 = preprocess(images, is_train)
    '''
    logits = network(images1, images2)
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=labels, logits=logits))
    inference = tf.nn.softmax(logits)

    optimizer = tf.train.MomentumOptimizer(FLAGS.learning_rate, momentum=0.9)
    train = optimizer.minimize(loss)
    '''

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())

        batch_images, batch_labels = cuhk03_dataset.read_data(FLAGS.data_dir, 'val', val_num_id,
            IMAGE_WIDTH, IMAGE_HEIGHT, FLAGS.batch_size)
        feed_dict = {learning_rate: FLAGS.learning_rate, images: batch_images,
                     labels: batch_labels, is_train: False}
        rs = sess.run(images1, feed_dict=feed_dict)
        print(rs)
        exit()

        for i in xrange(FLAGS.max_steps):
            batch_images, batch_labels = cuhk03_dataset.read_data(FLAGS.data_dir, 'train', tarin_num_id,
                IMAGE_WIDTH, IMAGE_HEIGHT, FLAGS.batch_size)
            feed_dict = {learning_rate: FLAGS.learning_rate, images: batch_images,
                labels: batch_labels, is_train: True}
            sess.run(train, feed_dict=feed_dict)
            train_loss = sess.run(loss, feed_dict=feed_dict)
            print('Step: %d, Train loss: %f' % (i, train_loss))

            if i % 500 == 0:
                batch_images, batch_labels = cuhk03_dataset.read_data(FLAGS.data_dir, 'val', val_num_id,
                    IMAGE_WIDTH, IMAGE_HEIGHT, FLAGS.batch_size)
                feed_dict = {learning_rate: FLAGS.learning_rate, images: batch_images,
                    labels: batch_labels, is_train: False}
                val_loss = sess.run(loss, feed_dict=feed_dict)
                print('Step: %d, Val loss: %f' % (i, val_loss))

if __name__ == '__main__':
    tf.app.run()
