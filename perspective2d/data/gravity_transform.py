import h5py
import numpy as np
import torch
from sklearn.preprocessing import normalize

from perspective2d.utils import decode_bin, encode_bin
from perspective2d.utils.panocam import PanoCam


def read_hdf5(path):
    with h5py.File(path, "r") as f:
        return f["dataset"][:]


class GravityTransform:
    def __init__(self, cfg, is_train=True):
        """
        Args:
            cfg (CfgNode): model configurations
            is_train (bool, optional): Defaults to True.

        Raises:
            NotImplementedError: cfg.MODEL.GRAVITY_DECODER.NUM_CLASSES must be in the set {"PerspectiveNet", "PersFormer", "ParamNetStandalone"}
        """
        self.resize = cfg.DATALOADER.RESIZE
        self.img_format = cfg.INPUT.FORMAT
        if cfg.MODEL.META_ARCHITECTURE == "PerspectiveNet":
            self.num_class = cfg.MODEL.FPN_GRAVITY_HEAD.NUM_CLASSES
        elif cfg.MODEL.META_ARCHITECTURE == "PersFormer":
            self.num_class = cfg.MODEL.GRAVITY_DECODER.NUM_CLASSES
        elif cfg.MODEL.META_ARCHITECTURE == "ParamNetStandalone":
            self.num_class = cfg.MODEL.GRAVITY_DECODER.NUM_CLASSES
        else:
            raise NotImplementedError
        self.is_train = is_train
        self.loss_type = cfg.MODEL.GRAVITY_DECODER.LOSS_TYPE

    def get_input_label(self, dataset_dict):
        """Retrieves ground truth gravity field

        Args:
            dataset_dict (dict): dict corresponding to one input example

        Returns:
            absvvp [float, float, float]: absolute vertical vanishing point
            gt_gfield_original (np.ndarray): ground truth gravity field
        """
        if dataset_dict["dataset"] in [
            "cities360",
            "rgbdpano",
            "sun360",
            "tartanair",
            "stanford2d3d",
            "objectron",
            "gsv",
            "edina",
        ]:
            r = dataset_dict["roll"]
            p = dataset_dict["pitch"]
            f = dataset_dict["vfov"]
            horizon = PanoCam.getRelativeHorizonLineFromAngles(
                elevation=p / 180 * np.pi,
                roll=r / 180 * np.pi,
                vfov=f / 180 * np.pi,
                im_h=dataset_dict["height"],
                im_w=dataset_dict["width"],
            )
            vvp = PanoCam.getRelativeVVP(
                elevation=p / 180 * np.pi,
                roll=r / 180 * np.pi,
                vfov=f / 180 * np.pi,
                im_h=dataset_dict["height"],
                im_w=dataset_dict["width"],
            )
            absvvp = PanoCam.getAbsVVP(
                im_h=dataset_dict["height"],
                im_w=dataset_dict["width"],
                horizon=horizon,
                vvp=vvp,
            )
        elif dataset_dict["dataset"] == "hypersim":
            absvvp = dataset_dict["vvp_abs"]
        elif dataset_dict["dataset"] in [
            "sun360_warp",
            "sun360_crop",
            "sun360_uncrop",
            "tartanair_warp",
            "tartanair_crop",
            "stanford2d3d_warp",
            "stanford2d3d_crop",
            "objectron_crop",
            "objectron_crop_mask",
            "gsv_crop",
            "edina_crop",
        ]:
            absvvp = dataset_dict["vvp_abs"]
        elif dataset_dict["dataset"] in ["coco-pseudo"]:
            pass
        elif dataset_dict["dataset"] in ["cities360_distort"]:
            absvvp = [0, 0, 0]
        else:
            raise NotImplementedError

        if self.is_train:
            if dataset_dict["dataset"] not in ["cities360_distort"]:
                gt_gfield_original = None
        else:
            if dataset_dict["dataset"] not in ["cities360_distort"]:
                gt_gfield_original = PanoCam.getGravityField(
                    im_h=dataset_dict["height"],
                    im_w=dataset_dict["width"],
                    absvvp=absvvp,
                )
        if dataset_dict["dataset"] in ["coco-pseudo"]:
            absvvp = [0, 0, 0]
            gt_gfield_original = read_hdf5(dataset_dict["gravity_file_name"]).transpose(
                1, 2, 0
            )
        elif dataset_dict["dataset"] in ["cities360_distort"]:
            absvvp = [0, 0, 0]
            gt_gfield_original = read_hdf5(dataset_dict["gravity_file_name"]).astype(
                "float32"
            )

        return absvvp, gt_gfield_original

    def absvvp_to_arrow(self, im_h, im_w, absvvp):
        """Convert absolute vertical vanishing point to arrow map

        Args:
            im_h (int): image height
            im_w (int): image width
            absvvp ([float, float, float]): absolute vertival vanishing

        Returns:
            np.ndarray: arrow map
        """
        gridx, gridy = np.meshgrid(np.arange(0, im_w), np.arange(0, im_h))
        start = np.stack((gridx.reshape(-1), gridy.reshape(-1))).T
        arrow = normalize(absvvp[:2] - start) * absvvp[2]
        arrow_map = arrow.reshape(im_h, im_w, 2)

        return arrow_map

    def encode_bin(self, gfield):
        """bin gravity field

        Args:
            gfield (torch.Tensor): gravity field

        Returns:
            torch.Tensor: binned gravity field of shape (1, h, w)
        """
        gfield_binned = encode_bin(gfield, self.num_class)
        return gfield_binned

    def to_tensor(self, im_h, im_w, absvvp):
        """Convert absvvp to gravity field and bin if using classification

        Args:
            im_h (int): image height
            im_w (int): image width
            absvvp ([float, float, float]): absolute vertical vanshing point

        Returns:
            torch.Tensor: gravity field, binned if using classification (1, h, w)
        """
        gfield = self.absvvp_to_arrow(im_h, im_w, absvvp)
        gfield = torch.as_tensor(gfield.transpose(2, 0, 1).astype("float32"))
        if self.loss_type == "regression":
            pass
        elif self.loss_type == "classification":
            gfield = self.encode_bin(gfield)
        return gfield

    def to_tensor_from_field(self, im_h, im_w, gfield):
        """Convert gravity field to tensor

        Args:
            im_h (int): image height
            im_w (int): image width
            gfield (np.ndarray): gravity field

        Returns:
            torch.Tensor:  gravity field, binned if using classification (1, h, w)
        """
        gfield = torch.as_tensor(gfield.transpose(2, 0, 1).astype("float32"))
        if self.loss_type == "regression":
            pass
        elif self.loss_type == "classification":
            gfield = self.encode_bin(gfield)
        return gfield
