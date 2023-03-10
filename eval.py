

"""
Add notes.
"""
import os
import numpy as np
import cv2
import h5py
from src.config import config
from src.model import HMRNetBase
from src.util import calc_temp_ab2, cut_image
import mindspore.dataset.vision.py_transforms as py_vision
import mindspore.dataset as ds
from mindspore import load_checkpoint, ops, set_seed
set_seed(1234)


class Hum36mDataloaderP2:
    def __init__(
            self,
            dataset_path,
            is_crop,
            scale_change,
            is_flip,
            minpoints,
            pixelformat='NHWC',
            Normalization=False,
            pro_flip=0.3):
        self.data_folder = dataset_path
        self.is_crop = is_crop
        self.scale_change = scale_change
        self.is_flip = is_flip
        self.pro_flip = pro_flip
        self.minpoints = minpoints
        self.pixelformat = pixelformat
        self.Normalization = Normalization
        self.Tensor = py_vision.ToTensor()
        self._load_Dataset()

    def _load_Dataset(self):
        self.images = []
        self.kp2ds = []
        self.boxs = []
        self.kp3ds = []
        self.shapes = []
        self.poses = []

        print('start loading hum3.6m data.')

        anno_file_path = os.path.join(self.data_folder, 'annot.h5')
        with h5py.File(anno_file_path) as fp:
            total_kp2d = np.array(fp['gt2d'])
            total_kp3d = np.array(fp['gt3d'])
            total_shap = np.array(fp['shape'])
            total_pose = np.array(fp['pose'])
            total_image_names = np.array(fp['imagename'])

            assert len(total_kp2d) == len(total_kp3d) and len(total_kp2d) == len(total_image_names) and \
                len(total_kp2d) == len(total_shap) and len(total_kp2d) == len(total_pose)

            l = len(total_kp2d)

            def _collect_valid_pts(pts):
                r = []
                for pt in pts:
                    if pt[2] != 0:
                        r.append(pt)
                return r

            for index in range(l):
                if '_3_' in total_image_names[index].decode():
                    kp2d = total_kp2d[index]
                    if np.sum(kp2d[:, 2]) < self.minpoints:
                        continue
                    lt, rb, _ = calc_temp_ab2(_collect_valid_pts(kp2d))
                    self.kp2ds.append(
                        np.array(kp2d.copy().reshape(-1, 3), dtype=np.float))
                    self.boxs.append((lt, rb))
                    self.kp3ds.append(total_kp3d[index].copy().reshape(-1, 3))
                    self.shapes.append(total_shap[index].copy())
                    self.poses.append(np.sum(total_pose[index].copy(), axis=0))
                    self.images.append(
                        os.path.join(
                            self.data_folder,
                            'images',
                            total_image_names[index].decode()))

        print('finished load hum3.6m data, total {} samples'.format(len(self.kp3ds)))

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        image_path = self.images[index]
        kps = self.kp2ds[index].copy()
        box = self.boxs[index]
        kp_3d = self.kp3ds[index].copy()
        np.random.seed(1234)
        scale = np.random.rand(
            4) * (self.scale_change[1] - self.scale_change[0]) + self.scale_change[0]
        originImage = cv2.imread(image_path)
        originImage = cv2.cvtColor(originImage, cv2.COLOR_BGR2RGB)
        image, kps = cut_image(originImage, kps, scale, box[0], box[1])
        ratio = 1.0 * config.crop_size / image.shape[0]
        kps[:, :2] *= ratio

        trivial, shape, pose = np.zeros(
            3), self.shapes[index], self.poses[index]
        theta = np.concatenate((trivial, pose, shape), 0)
        ratio = 1.0 / config.crop_size
        kps[:, :2] = 2.0 * kps[:, :2] * ratio - 1.0
        dst_image = cv2.resize(
            image,
            (config.crop_size,
             config.crop_size),
            interpolation=cv2.INTER_CUBIC)
        dst_image = self.Tensor(dst_image)
        data_ = {
            'kp_2d': kps,
            'kp_3d': kp_3d,
            'theta': theta,
            'image_name': self.images[index],
            'w_smpl': np.array([1.0]),
            'w_3d': np.array([1.0]),
            'data_set': 'hum3.6m'}

        label = np.concatenate(
            (data_['kp_2d'].flatten(),
             data_['kp_3d'].flatten(),
             data_['theta'],
             data_['w_smpl'],
             data_['w_3d']),
            axis=0).astype(
                np.float32)
        return dst_image, label


class CalcAccuracy():
    def __init__(self):
        super(CalcAccuracy, self).__init__()
        self.oprm = ops.ReduceSum(keep_dims=True)
        self.op = ops.Concat(0)
        self.abs = ops.Abs()
        self.expand_dims = ops.ExpandDims()
        self.reshape = ops.Reshape()

    def __call__(self, dataset, genera):
        MPJPE = []
        print('=========waiting=========')
        for data_ in dataset.create_dict_iterator():

            data_3d_data, data_3d_label = data_['data'], data_['label']

            sample_3d_count = data_3d_data.shape[0]

            w_3d = data_3d_label[:, -1]

            real_3d = data_3d_label[:, 42:42 +
                                    42].reshape(sample_3d_count, -1, 3)

            generator_outputs = genera(data_3d_data)

            predict_j3d = generator_outputs[3]

            loss_kp_3d = self.batch_kp_3d_l2_loss(
                real_3d, predict_j3d[:, :14, :], w_3d) * 1000

            MPJPE.append(loss_kp_3d.asnumpy())

        return MPJPE

    def batch_kp_3d_l2_loss(self, real_3d_kp, fake_3d_kp, w_3d):

        shape = real_3d_kp.shape
        k = self.oprm(w_3d) * shape[1] * 3.0 * 2.0 + 1e-8

        real_3d_kp, fake_3d_kp = self.align_by_pelvis(
            real_3d_kp), self.align_by_pelvis(fake_3d_kp)
        kp_gt = real_3d_kp
        kp_pred = fake_3d_kp
        kp_dif = (kp_gt - kp_pred)**2

        return ops.matmul(kp_dif.sum(1).sum(1), w_3d) * 1.0 / k

    def align_by_pelvis(self, joints):

        joints = self.reshape(joints, (joints.shape[0], 14, 3))
        pelvis = (joints[:, 3, :] + joints[:, 2, :]) / 2.0
        return joints - self.expand_dims(pelvis, 1)


if __name__ == '__main__':
    Cal = CalcAccuracy()

    DatasetHum = Hum36mDataloaderP2(
        dataset_path=config.dataset_path['hum3.6m'],
        is_crop=True,
        scale_change=[1.1, 1.2],
        is_flip=True,
        minpoints=5,
        pixelformat='NCHW',
        Normalization=True,
        pro_flip=0.5,
    )

    data = ds.GeneratorDataset(DatasetHum, ["data", "label"],
                               shuffle=True,
                               )
    data = data.batch(drop_remainder=True,
                      batch_size=32,
                      num_parallel_workers=config.num_worker,
                      python_multiprocessing=False)
    generator = HMRNetBase()

    load_checkpoint(config.checkpoint_file_path,
                    generator)
    generator.set_train(False)
    print('waiting')
    Acc = Cal(data, generator)
    print('PA-MPJPE is : ', np.mean(np.array(Acc)))
