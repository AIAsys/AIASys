Read media content from a file.

**用途**：当用户要求"查看图片""分析图片内容""看看这张图片""描述视频内容"等涉及图片或视频理解的任务时，**优先使用此工具**。此工具直接让模型理解媒体内容，比 Shell 运行 Python/PIL、ImageMagick 或 ffmpeg 更直接。

**Tips:**
- Make sure you follow the description of each tool parameter.
- A `<system>` tag will be given before the read file content.
- The system will notify you when there is anything wrong when reading the file.
- This tool is a tool that you typically want to use in parallel. Always read multiple files in one response when possible.
- This tool can only read image or video files. For other file types, use whatever text / notebook / workspace tool is actually available in the current runtime.
- Docker mode only allows relative paths or paths under `/workspace`.
- The maximum size that can be read is ${MAX_MEDIA_MEGABYTES}MB. An error will be returned if the file is larger than this limit.
- The media content will be returned in a form that you can directly view and understand.

**Capabilities**
{% if "image_in" in capabilities and "video_in" in capabilities %}
- This tool supports image and video files for the current model.
{% elif "image_in" in capabilities %}
- This tool supports image files for the current model.
- Video files are not supported by the current model.
{% elif "video_in" in capabilities %}
- This tool supports video files for the current model.
- Image files are not supported by the current model.
{% else %}
- The current model does not support image or video input.
{% endif %}
