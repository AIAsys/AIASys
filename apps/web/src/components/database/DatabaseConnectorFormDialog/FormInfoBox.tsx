export function FormInfoBox() {
  return (
    <div className="rounded-lg border border-border bg-muted/20 px-3 py-3 text-xs leading-5 text-muted-foreground">
      <p>
        这里录入的是目标数据库已有账号，平台不会替你创建远端用户或角色。
      </p>
      <p className="mt-1">
        所有连接默认只读，写入权限由目标数据库账号自身控制。
      </p>
    </div>
  );
}
