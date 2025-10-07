import os
import glob
import re

# 目标目录
TARGET_DIR = "arxiv_paper"

def delete_single_category_files(directory):
    """
    删除目录中所有单类别的 .json 文件。
    文件名模式: cs.XX_paper_YYYY-MM-DD.json
    """
    # 正则表达式匹配单类别文件名
    # 它会匹配 "cs.AI_paper..." 但不匹配 "cs.AI_cs.CL_paper..."
    pattern = re.compile(r"^(cs\.[A-Z]{1,2})_paper_(\d{4}-\d{2}-\d{2})\.json$")
    
    files_to_check = glob.glob(os.path.join(directory, "*.json"))
    
    if not files_to_check:
        print(f"在目录 '{directory}' 中没有找到 .json 文件。")
        return
        
    print(f"开始扫描目录以删除单类别文件: {directory}")
    
    deleted_count = 0
    for filepath in files_to_check:
        filename = os.path.basename(filepath)
        if pattern.match(filename):
            try:
                os.remove(filepath)
                print(f"🗑️  已删除冗余文件: '{filename}'")
                deleted_count += 1
            except OSError as e:
                print(f"❌  删除文件 '{filename}' 时出错: {e}")

    if deleted_count > 0:
        print(f"\n🎉 完成！总共删除了 {deleted_count} 个单类别文件。")
    else:
        print("\n👍 目录中没有找到需要删除的单类别文件。")

if __name__ == "__main__":
    if not os.path.isdir(TARGET_DIR):
        print(f"错误: 目录 '{TARGET_DIR}' 不存在。")
    else:
        delete_single_category_files(TARGET_DIR)
