// samples/counter.ets
// 计数器组件：@State 状态、方法、模板字符串、if-else、箭头函数

@Entry
@Component
struct Counter {
  @State count: number = 0;
  @Prop step: number = 1;

  increment(step: number): void {
    this.count = this.count + step;
  }

  build() {
    Column() {
      Text(`Count: ${this.count}`)
        .fontSize(20)
      Button('+1')
        .onClick(() => {
          this.increment(this.step);
        })
      if (this.count > 10) {
        Text('Big')
      } else {
        Text('Small')
      }
    }
  }
}