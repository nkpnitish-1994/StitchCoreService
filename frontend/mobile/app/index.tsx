import { Link } from "expo-router";
import { SafeAreaView, StyleSheet, Text, View } from "react-native";
export default function Home(){return <SafeAreaView style={styles.page}><Text style={styles.brand}>STITCHCORE</Text><Text style={styles.title}>Clothes that fit, without the errand.</Text><View style={styles.card}><Link href="/(customer)/new-order">Customer: create an order</Link></View><View style={styles.card}><Link href="/(logistics)/today">Logistics: today’s tasks</Link></View></SafeAreaView>};const styles=StyleSheet.create({page:{padding:24,gap:22,flex:1,backgroundColor:"#f6f2e9"},brand:{fontWeight:"800",color:"#0f5b3f"},title:{fontSize:34,fontWeight:"700"},card:{padding:20,backgroundColor:"#fff",borderRadius:8}});

