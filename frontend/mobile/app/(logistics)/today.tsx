import { Link } from "expo-router";
import { SafeAreaView, Text, View, StyleSheet } from "react-native";
const tasks=[{id:"demo-1",kind:"Pickup",customer:"Demo customer",time:"5:00–8:00 PM"},{id:"demo-2",kind:"Delivery",customer:"Demo customer",time:"Tomorrow"}];
export default function Today(){return <SafeAreaView style={s.page}><Text style={s.title}>Today’s tasks</Text>{tasks.map(t=><View style={s.card} key={t.id}><Text style={s.kind}>{t.kind}</Text><Text>{t.customer}</Text><Text>{t.time}</Text><Link href={`/(logistics)/task/${t.id}`}>Open task</Link></View>)}</SafeAreaView>};const s=StyleSheet.create({page:{padding:20,gap:12,backgroundColor:"#f6f2e9",flex:1},title:{fontSize:28,fontWeight:"700"},card:{padding:16,backgroundColor:"#fff",borderRadius:8,gap:4},kind:{fontWeight:"700",color:"#0f5b3f"}});

