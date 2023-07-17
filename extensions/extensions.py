""" Extensions to include as modules """  # 包含的扩展作为模块
# 由 WSH032 慷慨提供: graciously provided by WSH032
import os
import logging
from typing import Dict, Callable, List
import sys
from collections import OrderedDict


from extensions.extensions_tools import extensions_dir
from extensions.extensions_ui import (
    ui_sd_webui_infinite_image_browsing,
)

# 注册的扩展名字列表，键名请保证与文件夹同名
# List of registered extensions, please ensure key are as folder names
registered_extensions = OrderedDict(
    sd_webui_infinite_image_browsing=ui_sd_webui_infinite_image_browsing,
)


def disable_extensions(
    registered: Dict[str, Callable], cmd_opts_dict: dict
) -> Dict[str, Callable]:
    """Disable extensions"""  # 禁用扩展
    # 请保证所 pop 的键名与 registered_extensions 中的键名相同
    # 用硬编码以保证当 extensions_preload 或者 registered_extensions键名发生更改时候引发错误
    # Please ensure that the key name of pop is the same as the key name in
    # registered_extensions. Use hard coding to ensure that an error is thrown
    # when extensions_preload or registered_extensions key names change
    if cmd_opts_dict["disable_image_browsing"]:
        registered.pop("sd_webui_infinite_image_browsing")

    return registered


def check_extensions(
    registered: Dict[str, Callable]
) -> Dict[str, Callable]:
    """Check if all extensions exist"""  # 检查是否扩展都存在
    extensions_dir_list = os.listdir(extensions_dir)
    not_exist_extensions_list = []

    # 获取字典的所有键名: Get all key names of the dictionary
    registered_extensions_name_list = list(registered.keys())
    # 正在检查扩展是否存在于extensions文件夹中:
    print("Checking if the extension exists in the extensions folder")
    # 请勿更改extensions文件夹中的文件名\n...:
    print("Please do not change the file name in the extensions folder\n"
          f"{registered_extensions_name_list}")

    # 检查字典中相应的键名是否存在于extensions文件夹中，不在就删除字典中相应的键
    # 遍历字典中的键
    # Check whether the corresponding key name in the dictionary exists in the
    # extensions folder, and delete the corresponding key in the dictionary if
    # it does not exist; Traverse the keys in the dictionary
    for extension in list(registered.keys()):
        # 检查键是否在列表中: Check if the key is in the list
        if extension not in extensions_dir_list:
            # 删除字典中的键: Delete the key in the dictionary
            registered.pop(extension)
            # del registered[extension]
            # 记录不存在的扩展名: Record the non-existent extension name
            not_exist_extensions_list.append(extension)
    if not_exist_extensions_list:
        # 以下扩展不存在于extensions文件夹中，将不会被载入:
        logging.error("Extensions are misplaced or missing: %s",
                      not_exist_extensions_list)

    return registered


# TODO: 最好是调用某个扩展的时候再修改相应的sys.path，而不是一次性修改全部
# TODO: The best way is to modify the corresponding sys.path when calling an
# extension, rather than modifying all at once
def sys_path_for_extensions() -> List[str]:
    # 将每个扩展的所在的文件夹添加到sys.path中，以便各扩展可以正常import
    # Returns: List[str]: 改变之前的sys.path.copy()
    """Add the folder where each extension is located to sys.path so that each
    extension can be imported normally

    Returns:
        List[str]: sys.path.copy() before the change
    """
    sys_path = sys.path.copy()

    for extension in registered_extensions:
        # 让扩展在前面: Place the extension up front
        sys.path = [os.path.join(extensions_dir, extension)] + sys.path

    return sys_path
