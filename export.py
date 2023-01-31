

from src.config import config
from src.model import HMRNetBaseExport
import mindspore as ms


def run_export():
    """run export."""
    generator = HMRNetBaseExport()

    assert config.checkpoint_file_path is not None, "checkpoint_path is None."

    param_dict = ms.load_checkpoint(config.checkpoint_file_path)

    result = {}
    for k in param_dict.keys():
        if 'smpl' not in k:
            result[k] = param_dict[k]
    ms.load_param_into_net(generator, result)
    input_arr = ms.numpy.zeros(
        [
            config.batch_size +
            config.batch_3d_size,
            3,
            config.crop_size,
            config.crop_size],
        ms.float32)
    ms.export(
        generator,
        input_arr,
        file_name=config.file_name,
        file_format=config.file_format)


if __name__ == '__main__':
    run_export()
