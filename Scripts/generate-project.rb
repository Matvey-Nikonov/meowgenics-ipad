#!/usr/bin/env ruby
require 'xcodeproj'

root = File.expand_path('..', __dir__)
project_path = File.join(root, 'MewgenicsIPad.xcodeproj')
abort 'Project already exists; edit it in place instead of replacing user settings.' if File.exist?(project_path)
project = Xcodeproj::Project.new(project_path)
target = project.new_target(:application, 'MewgenicsIPad', :ios, '17.0')
group = project.main_group.new_group('MewgenicsIPad', 'MewgenicsIPad')
Dir.glob(File.join(root, 'MewgenicsIPad', '**', '*.swift')).sort.each do |path|
  reference = group.new_file(path.delete_prefix(File.join(root, 'MewgenicsIPad') + '/'))
  target.source_build_phase.add_file_reference(reference)
end
target.build_configurations.each do |config|
  config.build_settings.merge!({
    'PRODUCT_BUNDLE_IDENTIFIER' => 'org.example.mewgenics.inspector',
    'PRODUCT_NAME' => 'MewgenicsIPad',
    'SWIFT_VERSION' => '5.0',
    'SWIFT_OBJC_BRIDGING_HEADER' => 'MewgenicsIPad/Core/ZlibBridge.h',
    'OTHER_LDFLAGS' => '$(inherited) -lz',
    'TARGETED_DEVICE_FAMILY' => '2',
    'GENERATE_INFOPLIST_FILE' => 'YES',
    'INFOPLIST_KEY_CFBundleDisplayName' => 'Mewgenics Port',
    'INFOPLIST_KEY_UIApplicationSceneManifest_Generation' => 'YES',
    'INFOPLIST_KEY_UILaunchScreen_Generation' => 'YES',
    'INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad' => 'UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight UIInterfaceOrientationPortrait UIInterfaceOrientationPortraitUpsideDown',
    'INFOPLIST_KEY_LSSupportsOpeningDocumentsInPlace' => 'YES',
    'CODE_SIGN_STYLE' => 'Automatic',
    'CURRENT_PROJECT_VERSION' => '1',
    'MARKETING_VERSION' => '0.1.0',
    'CLANG_CXX_LANGUAGE_STANDARD' => 'c++20',
    'SUPPORTED_PLATFORMS' => 'iphoneos iphonesimulator',
    'SUPPORTS_MACCATALYST' => 'NO',
    'ENABLE_USER_SCRIPT_SANDBOXING' => 'YES'
  })
end
project.save
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(target)
scheme.set_launch_target(target)
scheme.save_as(project_path, 'MewgenicsIPad', true)
puts project_path
