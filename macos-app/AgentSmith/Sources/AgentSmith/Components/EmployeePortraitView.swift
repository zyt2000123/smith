import AppKit
import SwiftUI

struct EmployeePortraitView: View {
    let imageName: String?
    let fallbackColor: Color
    let fallbackText: String
    let width: CGFloat
    let height: CGFloat
    let cornerRadius: CGFloat

    var body: some View {
        Group {
            if let imageName,
               let url = Bundle.module.url(forResource: imageName, withExtension: "png", subdirectory: "Employees"),
               let nsImage = NSImage(contentsOf: url) {
                Image(nsImage: nsImage)
                    .resizable()
                    .scaledToFit()
            } else {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(fallbackColor.gradient)
                    .overlay(
                        Text(fallbackText)
                            .font(.system(size: width * 0.28, weight: .bold))
                            .foregroundStyle(.white)
                    )
            }
        }
        .frame(width: width, height: height)
    }
}
