import os
import glob
import re

# 目标目录
TARGET_DIR = "arxiv_paper"

def rename_files_in_directory(directory):
    """
    重命名目录中日期格式不规范的 .json 文件。
    将 YYYYMMDD 格式的日期转换为 YYYY-MM-DD。
    """
    # 正则表达式匹配 YYYYMMDD 格式
    pattern = re.compile(r"(\S+_)(\d{8})(\.json)$")
    
    # 查找所有 .json 文件
    files_to_check = glob.glob(os.path.join(directory, "*.json"))
    
    if not files_to_check:
        print(f"在目录 '{directory}' 中没有找到 .json 文件。")
        return
        
    print(f"开始扫描目录: {directory}")
    
    renamed_count = 0
    for filepath in files_to_check:
        filename = os.path.basename(filepath)
        match = pattern.match(filename)
        
        if match:
            prefix = match.group(1)
            date_str = match.group(2)
            suffix = match.group(3)
            
            try:
                # 解析并重新格式化日期
                year = date_str[0:4]
                month = date_str[4:6]
                day = date_str[6:8]
                new_date_str = f"{year}-{month}-{day}"
                
                # 构建新文件名
                new_filename = f"{prefix}{new_date_str}{suffix}"
                new_filepath = os.path.join(directory, new_filename)
                
                # 检查新文件是否已存在
                if os.path.exists(new_filepath):
                    print(f"⚠️  跳过重命名: 新文件名 '{new_filename}' 已存在。将删除旧文件 '{filename}'。")
                    os.remove(filepath)
                else:
                    # 重命名文件
                    os.rename(filepath, new_filepath)
                    print(f"✅  重命名: '{filename}' -> '{new_filename}'")
                    renamed_count += 1
            
            except Exception as e:
                print(f"❌  处理文件 '{filename}' 时出错: {e}")

    if renamed_count > 0:
        print(f"\n🎉 完成！总共重命名了 {renamed_count} 个文件。")
    else:
        print("\n👍 目录中的文件名格式均符合规范，无需重命名。")

if __name__ == "__main__":
    if not os.path.isdir(TARGET_DIR):
        print(f"错误: 目录 '{TARGET_DIR}' 不存在。")
    else:
        rename_files_in_directory(TARGET_DIR)
