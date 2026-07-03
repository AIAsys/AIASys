const { execSync } = require('child_process');

// 查找所有 AIASys 相关进程
const cmd = `powershell -NoProfile -Command "Get-Process | Where-Object { $_.Path -like '*AIASys*' -or $_.Name -like '*AIASys*' -or $_.Name -like '*electron*' } | Select-Object ProcessId, Name, Path | ConvertTo-Json"`;
try {
    const output = execSync(cmd, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
    const processes = JSON.parse(output);
    if (Array.isArray(processes)) {
        processes.forEach(p => {
            console.log(`Found: ${p.Name} (PID ${p.ProcessId}) - ${p.Path}`);
            try {
                execSync(`taskkill /PID ${p.ProcessId} /F`, { stdio: 'pipe' });
                console.log(`Killed PID ${p.ProcessId}`);
            } catch (e) {
                console.log(`Failed to kill PID ${p.ProcessId}: ${e.message}`);
            }
        });
    } else {
        console.log('No AIASys/electron processes found');
    }
} catch (e) {
    console.log('Error:', e.message);
}
