// samples/hello.ets
// 最小鸿蒙组件：装饰器 + struct + build() + 声明式 UI

@Entry
@Component
struct HelloPage {
  @State message: string = 'Hello ArkTS';

  build() {
    Column() {
      Text(this.message)
        .fontSize(24)
        .fontWeight(FontWeight.Bold)
      Button('Click Me')
        .onClick(() => {
          this.message = 'Clicked';
        })
    }
  }
}