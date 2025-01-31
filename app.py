from flask import Flask, render_template, request, send_file, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
import os
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import io
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 添加这行，确保JSON正确处理中文

# 更新CORS配置
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# 允许的文件类型
ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html', charset='UTF-8')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有选择文件'}), 400
            
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
            
        if not file.filename.lower().endswith(('.jpg', '.jpeg')):
            return jsonify({'error': '只支持JPG/JPEG格式'}), 400
            
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        # 修改返回的filepath格式
        return jsonify({
            'success': True,
            'filename': unique_filename,
            'filepath': unique_filename  # 只返回文件名，不返回完整路径
        })
        
    except Exception as e:
        print(f"上传错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """处理图片预览请求"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/remove-file', methods=['POST', 'OPTIONS'])
def remove_file():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.get_json()
        filename = data.get('file')
        
        if not filename:
            print("错误：未指定文件名")  # 添加调试信息
            return jsonify({'error': '未指定文件'}), 400
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        print(f"尝试删除文件: {filepath}")  # 添加调试信息
        
        if not os.path.exists(filepath):
            print(f"错误：文件不存在: {filepath}")  # 添加调试信息
            return jsonify({'error': '文件不存在'}), 404
        
        os.remove(filepath)
        print(f"成功删除文件: {filepath}")  # 添加调试信息
        return jsonify({'message': '文件已删除'})
    except Exception as e:
        print(f"删除错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

def compress_image(image, quality):
    """压缩图片"""
    img_buffer = io.BytesIO()
    # 转换为RGB模式（如果是RGBA）
    if image.mode in ('RGBA', 'P'):
        image = image.convert('RGB')
    # 保存时使用JPEG格式和指定的质量
    image.save(img_buffer, 'JPEG', quality=quality)
    img_buffer.seek(0)
    return img_buffer

@app.route('/convert', methods=['POST', 'OPTIONS'])
def convert_to_pdf():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.get_json()
        files = data.get('files', [])
        page_size = data.get('pageSize', 'A4')
        orientation = data.get('orientation', 'portrait')
        margins = data.get('margins', 20)
        compression_level = data.get('compression', 'medium')  # 新增压缩级别参数
        
        # 根据压缩级别设置图片质量
        quality_map = {
            'none': 100,
            'low': 85,
            'medium': 60,
            'high': 40
        }
        quality = quality_map.get(compression_level, 60)
        
        merger = PdfMerger()
        
        for filename in files:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # 打开图片
            with Image.open(filepath) as img:
                # 压缩图片
                img_buffer = compress_image(img, quality)
                
                # 转换为PDF
                pdf_buffer = io.BytesIO()
                compressed_img = Image.open(img_buffer)
                compressed_img.save(pdf_buffer, format='PDF', resolution=300.0)
                pdf_buffer.seek(0)
                merger.append(pdf_buffer)
        
        # 保存合并后的PDF到内存
        output_buffer = io.BytesIO()
        merger.write(output_buffer)
        merger.close()
        output_buffer.seek(0)
        
        # 清理临时文件
        for filename in files:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        return send_file(
            output_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='converted.pdf'
        )
    except Exception as e:
        print(f"转换错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/preview-size', methods=['POST'])
def preview_size():
    try:
        data = request.get_json()
        files = data.get('files', [])
        compression_level = data.get('compression', 'medium')
        
        quality_map = {
            'none': 100,
            'low': 85,
            'medium': 60,
            'high': 40
        }
        quality = quality_map.get(compression_level, 60)
        
        total_original_size = 0
        total_compressed_size = 0
        
        for filename in files:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                # 获取原始文件大小
                original_size = os.path.getsize(filepath)
                total_original_size += original_size
                
                # 计算压缩后大小
                with Image.open(filepath) as img:
                    compressed_buffer = compress_image(img, quality)
                    total_compressed_size += compressed_buffer.getbuffer().nbytes
        
        # 计算节省的空间百分比
        if total_original_size > 0:
            savings = ((total_original_size - total_compressed_size) / total_original_size) * 100
        else:
            savings = 0
            
        return jsonify({
            'originalSize': total_original_size,
            'compressedSize': total_compressed_size,
            'savings': savings
        })
        
    except Exception as e:
        print(f"预览大小错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
