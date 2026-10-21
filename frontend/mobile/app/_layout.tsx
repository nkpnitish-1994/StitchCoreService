import { Stack } from "expo-router";
export default function Layout(){return <Stack screenOptions={{headerStyle:{backgroundColor:"#0f5b3f"},headerTintColor:"#fff"}}><Stack.Screen name="index" options={{title:"StitchCore"}}/><Stack.Screen name="(customer)" options={{headerShown:false}}/><Stack.Screen name="(logistics)" options={{headerShown:false}}/></Stack>}

