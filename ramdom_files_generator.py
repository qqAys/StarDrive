import os
import random
import shutil
import string
from pathlib import Path


class TestLibraryGenerator:
    def __init__(
        self,
        root_name="test_library",
        max_depth=4,
        max_folders=3,
        max_files=5,
        clear_old=True,
    ):
        self.root_path = Path(os.getcwd()) / root_name
        self.max_depth = max_depth  # 最大目录深度
        self.max_folders = max_folders  # 每个目录下最大子文件夹数
        self.max_files = max_files  # 每个目录下最大文件数
        self.extensions = [".txt", ".log", ".md", ".py", ".json", ".csv"]
        self.clear_old = clear_old

        # 随机前缀
        self.words = [
            "alpha",
            "beta",
            "project",
            "data",
            "temp",
            "archive",
            "node",
            "core",
            "backup",
        ]

    def get_random_name(self, is_file=False):
        """生成随机名称"""
        prefix = random.choice(self.words)
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        name = f"{prefix}_{suffix}"
        if is_file:
            return name + random.choice(self.extensions)
        return name

    def create_random_content(self, file_path):
        """为文件写入随机内容"""
        content = f"This is a dummy file generated for testing.\nID: {random.getrandbits(32)}\n"
        content += "".join(random.choices(string.printable, k=100))
        file_path.write_text(content, encoding="utf-8")

    def generate_structure(self, current_path, current_depth):
        """递归生成目录结构"""
        if current_depth > self.max_depth:
            return

        # 创建文件夹
        num_folders = random.randint(1, self.max_folders)
        for _ in range(num_folders):
            subfolder = current_path / self.get_random_name()
            subfolder.mkdir(exist_ok=True)

            # 递归调用
            self.generate_structure(subfolder, current_depth + 1)

        # 创建文件
        num_files = random.randint(1, self.max_files)
        for _ in range(num_files):
            file_path = current_path / self.get_random_name(is_file=True)
            self.create_random_content(file_path)

    def run(self):
        """启动生成流程"""
        if self.clear_old:
            if self.root_path.exists():
                print(f"清理旧目录: {self.root_path}")
                shutil.rmtree(self.root_path)

        self.root_path.mkdir(exist_ok=True, parents=True)
        print(f"正在生成随机测试库于: {self.root_path} ...")
        self.generate_structure(self.root_path, 0)
        print("生成完毕！")


if __name__ == "__main__":
    generator = TestLibraryGenerator(
        root_name="app_data/storage/My_Complex_Library",
        max_depth=3,
        max_folders=4,
        max_files=6,
    )
    generator.run()
